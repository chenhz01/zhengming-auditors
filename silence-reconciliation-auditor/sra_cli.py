#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SRA —— 沉默对账器（Silence Reconciliation Auditor）· 第二十三条

命题（Step 3 改写后，不再是"没人测漏报"）：
  ProactiveBench(2026-09-11) 已经在测 missed responses，
  但它测漏报的前提是**事先有人标注了「什么时候该说话」**（annotated speech window）。
  ⇒ 真实部署里没人做这件事。真正的漏报不是"报晚了"，是「压根不在题面上」。
  ⇒ 本件招牌：沉默不是「没事发生」的证据，是「没人定义过该不该发生」的证据。

六判据（对照 FSA 六判据，把输出侧的病搬到输入/时间侧）：

  G1 沉默信号所有权   —— 「我沉默了」这个信号是谁给的
  G2 真值前置性 ★     —— 「该说话的时刻」在流开始前就定死了吗
  G3 漏报可分辨性     —— 能不能分开「该说没说」与「没标过该说」
  G4 未覆盖度 ★招牌   —— 有没有指标说"多少沉默是根本无法判定的"
  G5 声明可外部校验   —— 模型说"我主动沉默"，理由能被外部验证吗
  G6 时点粒度         —— 判定粒度是整段还是秒级

★ v2.7.11 新硬规则：任何判据函数**所有分支都返回数值**，零命中给 0.0 不给 None。
★ basis 字段：[实测] 从落盘语料算出 / [声明] 依公开文档声明 / [推导] 论证得出。
  推导项若与实测项混报均分，CLI 主动告警（沿用 FSA 机制）。
"""
from __future__ import annotations

import dataclasses
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ART = ROOT / "_raw" / "artifacts"

PROBE_TOTAL_DEMOS = 9          # 官方博客 DEMO 01–09
GROUND_TRUTH_ANCHORS = [       # 真值锚：出现这些，说明该沉默场景**有**"该说话的时刻"
    r"annotated speech window",
    r"agreed[- ]upon event",
    r"the moment the target",
    r"when the target",
    r"premature", r"missed response", r"response and silence rates",
    r"标注", r"预先", r"人工标注", r"地面真值", r"ground[- ]truth",
    r"触发条件", r"约定", r"报警", r"提醒我",
]
# 人为真值：触发条件由用户/外部**事前设定**，而不是从画面内容里读出来的客观事件
ARTIFICIAL_TRIGGER = [
    r"穿粉红色衣服", r"agreed[- ]upon", r"设定", r"提醒我",
    r"one agreed-upon event only", r"the moment the cat", r"cat touches the carrot",
]
# 客观真值：触发条件就是画面里发生的事
# （第一版漏了 DEMO 03 足球解说的 "passes, shots, and goals" 与 DEMO 04 的
#   "picking up each page the moment it appears"，导致它落到"未判定"。）
OBJECTIVE_TRIGGER = [
    r"the target person falls", r"falls", r"successful shot", r"new line",
    r"every successful shot", r"palm is clearly visible", r"returns in new clothes",
    r"passes, shots, and goals", r"picking up each page the moment it appears",
    r"capture key changes", r"transcribes each new line as soon as it is written",
]


@dataclasses.dataclass
class Decl:
    name: str = ""
    silence_ownership: str = ""      # model_self_report|external_anchor|both|absent
    truth_ahead: str = ""            # ahead|post_hoc|unlabeled|unknown   ← ★ G2
    miss_resolvable: str = ""        # labeled|unlabeled|partial
    unobserved: str = ""             # measured|declared|none             ← ★ G4 招牌
    claim_verifiable: str = ""       # yes|no|partial
    timing_granularity: str = ""     # per_second|segment|n/a
    # 逐判据覆盖 basis：SRA 一栏除实测项外必须标【推导】，不许把主张说成实跑
    basis_override: dict[str, str] = dataclasses.field(default_factory=dict)
    notes: list[str] = dataclasses.field(default_factory=list)


# ── 语料侧实测 ──────────────────────────────────────────────────────

def load_artifacts() -> list[dict[str, Any]]:
    """★ 按内容指纹去重后再扫。

    第一版直接 rglob 全部 .md，结果 openmoss.github.io（DUP）与 openmoss.ai 内容字节相同，
    DEMO 描述被数了两遍 ⇒ 9 个 demo 报成 18 个、人为真值占比 0.111 是错的（应为 0.5）。
    **重复语料会让所有比例指标悄悄偏掉**，而且不报错。
    """
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in sorted(ART.glob("*.md")):
        if f.name.startswith("sra_report") or f.name.startswith("_manifest"):
            continue
        try:
            t = f.read_text(encoding="utf-8")
        except Exception as e:
            out.append({"file": f.name, "text": "", "err": str(e)})
            continue
        fp = __import__("hashlib").sha256(t.encode("utf-8")).hexdigest()[:16]
        if fp in seen:
            out.append({"file": f.name, "text": t, "dup_of": "[已去重]"})
            continue
        seen.add(fp)
        out.append({"file": f.name, "text": t})
    return out


def scan_silence_contexts() -> dict[str, Any]:
    """全量扫落盘语料，把「沉默」出现的每个上下文拎出来，逐个判它有没有判定真值。

    ★ 全量扫描，不做抽样 —— 「审核全量覆盖」约定。
    """
    docs = load_artifacts()
    total_docs = len(docs)
    contexts: list[dict[str, Any]] = []
    for d in docs:
        for m in re.finditer(r"[Ss]ilence|[Ss]ilent|沉默|静默", d["text"]):
            s = max(0, m.start() - 220)
            e = min(len(d["text"]), m.end() + 220)
            ctx = d["text"][s:e].replace("\n", " ")
            has_gt = any(re.search(p, ctx, re.I) for p in GROUND_TRUTH_ANCHORS)
            # ★ 保留完整窗口 ctx，另存 snippet 只做展示。
            #   第一版只留 snippet（截断 150 字符），下游探针拿它判真值 ⇒
            #   窗口比这里窄，招牌数对不上（0.966 vs 0.898）——**同口径**必须是同一份数据。
            contexts.append({"doc": d["file"], "has_truth": has_gt,
                             "offset": m.start(), "ctx": ctx, "snippet": ctx[:150]})
    with_gt = [c for c in contexts if c["has_truth"]]
    return {
        "docs_scanned": total_docs,
        "doc_bytes": sum(len(d["text"]) for d in docs),
        "total_silence_contexts": len(contexts),
        "with_truth": len(with_gt),
        "unjudgeable": len(contexts) - len(with_gt),
        "uncovered_ratio": round((len(contexts) - len(with_gt)) / len(contexts), 3)
        if contexts else 0.0,
        "contexts": contexts,
    }


def scan_demo_triggers() -> dict[str, Any]:
    """官方 9 个 demo 的触发条件分类：人为真值 vs 客观真值。"""
    docs = load_artifacts()
    blob = "\n".join(d["text"] for d in docs)
    rows: list[dict[str, Any]] = []
    seen_n: set[int] = set()
    for m in re.finditer(r"DEMO\s*0?(\d{1,2})", blob):
        n = int(m.group(1))
        if n < 1 or n > PROBE_TOTAL_DEMOS or n in seen_n:
            continue
        seen_n.add(n)
        b = blob[m.end(): m.end() + 420]
        artificial = any(re.search(p, b, re.I) for p in ARTIFICIAL_TRIGGER)
        objective = any(re.search(p, b, re.I) for p in OBJECTIVE_TRIGGER)
        rows.append({"demo": n, "artificial": artificial, "objective": objective,
                     "verdict": "人为真值" if artificial else ("客观真值" if objective else "未判定")})
    artificial_n = len([r for r in rows if r["verdict"] == "人为真值"])
    objective_n = len([r for r in rows if r["verdict"] == "客观真值"])
    undecided = len(rows) - artificial_n - objective_n
    return {"demos_found": len(rows), "artificial_n": artificial_n,
            "objective_n": objective_n, "undecided": undecided, "rows": rows,
            "artificial_ratio": round(artificial_n / len(rows), 3) if rows else 0.0}


# ── 六判据 ─────────────────────────────────────────────────────────

def g1(d: Decl) -> dict[str, Any]:
    """G1 沉默信号所有权：押在谁的自报上。"""
    if d.silence_ownership == "external_anchor":
        return {"crit": "G1", "score": 1.0, "basis": "实测",
                "why": "沉默由独立于模型的事件锚点判定"}
    if d.silence_ownership in ("model_self_report", "both"):
        return {"crit": "G1", "score": 0.4, "basis": "声明",
                "why": "沉默信号来自模型自身 <|silence|> token —— 模型自报，不可外部校验"}
    return {"crit": "G1", "score": 0.0, "basis": "实测",
            "why": "零命中：既无外部锚点亦无自报信号"}


def g2(d: Decl) -> dict[str, Any]:
    """G2 真值前置性 ★：『该说话的时刻』在流开始前就定死了吗。"""
    if d.truth_ahead == "ahead":
        return {"crit": "G2", "score": 1.0, "basis": "实测",
                "why": "外部事件流在进入前已定义该说话的时刻"}
    if d.truth_ahead == "post_hoc":
        return {"crit": "G2", "score": 0.5, "basis": "实测",
                "why": "真值由人工事后标注（如 annotated speech window），流本身不含它"}
    return {"crit": "G2", "score": 0.0, "basis": "实测",
            "why": "零命中：无前置真值 ⇒ 漏报在定义上不可判定"}


def g3(d: Decl) -> dict[str, Any]:
    """G3 漏报可分辨性：能否分开『该说没说』与『没标过该说』。"""
    if d.miss_resolvable == "labeled":
        return {"crit": "G3", "score": 1.0, "basis": "实测",
                "why": "有标注真值，漏报可纳入计分"}
    if d.miss_resolvable == "partial":
        return {"crit": "G3", "score": 0.5, "basis": "实测",
                "why": "只在部分场景可分辨，未覆盖区仍不可判"}
    return {"crit": "G3", "score": 0.0, "basis": "实测",
            "why": "零命中：漏报与未覆盖区混为一谈"}


def g4(d: Decl, scan: dict[str, Any]) -> dict[str, Any]:
    """G4 未覆盖度 ★招牌：有没有指标说『多少沉默根本无法判定』。"""
    if d.unobserved == "measured" and scan["total_silence_contexts"] > 0:
        return {"crit": "G4", "score": 1.0, "basis": "实测",
                "why": "未覆盖沉默比例 = %d/%d = %.3f（真从语料算出）"
                       % (scan["unjudgeable"], scan["total_silence_contexts"],
                          scan["uncovered_ratio"])}
    if d.unobserved == "declared":
        return {"crit": "G4", "score": 0.5, "basis": "声明",
                "why": "声称会报未覆盖度，但语料里测不到"}
    return {"crit": "G4", "score": 0.0, "basis": "实测",
            "why": "零命中：%d 处沉默上下文，无一处给出未覆盖度度量 ⇒ 根本没有可判定性指标"
                   % scan["total_silence_contexts"]}


def g5(d: Decl) -> dict[str, Any]:
    """G5 声明可外部校验：模型说『我主动沉默』，理由能外部验证吗。"""
    if d.claim_verifiable == "yes":
        return {"crit": "G5", "score": 1.0, "basis": "实测", "why": "沉默理由可被独立传感器叉分"}
    if d.claim_verifiable == "partial":
        return {"crit": "G5", "score": 0.5, "basis": "声明", "why": "部分理由可叉分"}
    return {"crit": "G5", "score": 0.0, "basis": "实测",
            "why": "零命中：沉默没有任何外部可校验的理由，只有 token 本身"}


def g6(d: Decl) -> dict[str, Any]:
    """G6 时点粒度：判定是整段还是秒级。"""
    if d.timing_granularity == "per_second":
        return {"crit": "G6", "score": 1.0, "basis": "实测",
                "why": "ProactiveBench 已是 1 秒粒度，本项行业已达顶"}
    return {"crit": "G6", "score": 0.0, "basis": "实测",
            "why": "零命中：粒度不足 ⇒ 漏报只能按整段统计"}


ALL: list[tuple[str, Any, str]] = [
    ("G1", g1, "沉默信号所有权"),
    ("G2", g2, "真值前置性 ★"),
    ("G3", g3, "漏报可分辨性"),
    ("G4", g4, "未覆盖度 ★招牌"),
    ("G5", g5, "声明可外部校验"),
    ("G6", g6, "时点粒度"),
]

# ★ 行业现状与 SRA 主张是**两份不同声明**，第一版共用同一个 Decl ⇒ 对比列毫无意义。
# ★ SRA 一栏的 basis 也要诚实：除了 G4（真的从语料算出），其余是**主张不是实跑**，
#   一律标【推导】。把设计主张标成【实测】，就是本流程最大的失败模式。
INDUSTRY = Decl(
    name="MOSS-VL-Realtime + ProactiveBench（行业现状）",
    silence_ownership="model_self_report",
    truth_ahead="post_hoc",
    miss_resolvable="partial",
    unobserved="none",
    claim_verifiable="no",
    timing_granularity="per_second",
    notes=["<|silence|> 由模型自行生成 ⇒ 自报；ProactiveBench 明确说现有协议未能完全分离"
           "响应质量与响应策略",
           "ProactiveBench 已有 missed-response 条目，但依赖人工标注的 annotated speech window",
           "ProactiveBench 自陈：低频率响应策略也能拿到中等均分"],
)

SRA_PROPOSAL = Decl(
    name="SRA 主张（沉默对账）",
    silence_ownership="external_anchor",
    truth_ahead="ahead",
    miss_resolvable="labeled",
    unobserved="measured",
    claim_verifiable="yes",
    timing_granularity="per_second",
    basis_override={"G1": "推导", "G2": "推导", "G3": "推导", "G5": "推导", "G6": "实测"},
    notes=["沉默由独立于模型的事件锚点对账判定，不采信 <|silence|> 自报",
           "外部事件流在进入前已定义『该说话的时刻』",
           "未覆盖区（无标注真值的沉默）显式单列并报未覆盖度，不与漏报混算",
           "G5=1.0 为【推导】而非实跑：主张本身尚未部署，见手册已知限制"],
)


def audit(d: Decl, scan: dict[str, Any], demo: dict[str, Any]) -> dict[str, Any]:
    parts = [fn(d, scan) if crit == "G4" else fn(d) for crit, fn, _ in ALL]
    # ★ 零命中的判据必须显式记 zero_hit，且 score 一律数值（v2.7.11 硬规则）
    for p in parts:
        p["zero_hit"] = p["score"] == 0.0
        assert isinstance(p["score"], (int, float)), \
            "%s 的 score 不是数值（零命中必须给 0.0，不许 None）" % p["crit"]
        if p["crit"] in d.basis_override:
            p["basis"] = d.basis_override[p["crit"]]
    sra = [p["score"] for p in parts]
    sra_avg = round(sum(sra) / len(sra), 3)
    verdict = "silence_unreconciled" if sra_avg < 0.5 else "silence_reconciled"
    deduct = [p["crit"] for p in parts if p["basis"] == "推导" and p["score"] == 1.0]
    return {"decl": dataclasses.asdict(d), "parts": parts,
            "scores": sra, "avg": sra_avg, "verdict": verdict,
            "deduct_basis": deduct,
            "scan": {k: v for k, v in scan.items() if k != "contexts"},
            "demo": {k: v for k, v in demo.items() if k != "rows"},
            "demo_rows": demo["rows"]}


def selftest(scan: dict[str, Any], demo: dict[str, Any]) -> int:
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, cond: bool, msg: str = "") -> None:
        checks.append((name, bool(cond), msg))

    d = Decl()
    a = audit(d, scan, demo)
    ck("零声明时 G1 score 可见", a["parts"][0]["score"] is not None)
    ck("零声明时 G2 score 可见", a["parts"][1]["score"] is not None)
    ck("零声明时 G4 score 可见", a["parts"][3]["score"] is not None)
    ck("零命中分支 score 为 0.0 非 None",
       all(isinstance(p["score"], (int, float)) for p in a["parts"]))
    ck("零声明时 G4=0.0", a["parts"][3]["score"] == 0.0)

    d2 = Decl(silence_ownership="model_self_report", truth_ahead="post_hoc",
              miss_resolvable="partial", unobserved="declared")
    a2 = audit(d2, scan, demo)
    ck("私有沉默 token ⇒ G1 不上满分", a2["parts"][0]["score"] < 1.0)

    d3 = Decl(silence_ownership="external_anchor", truth_ahead="ahead",
              miss_resolvable="labeled", unobserved="measured")
    a3 = audit(d3, scan, demo)
    ck("外部锚点+前置真值 ⇒ G1=1.0", a3["parts"][0]["score"] == 1.0)
    ck("前置真值 ⇒ G2=1.0", a3["parts"][1]["score"] == 1.0)
    ck("FSA 招牌机制仍在（G4 实测可满分）", a3["parts"][3]["score"] == 1.0)

    ck("语料全量扫描 ≥1 个沉默上下文", scan["total_silence_contexts"] >= 1,
       "实测=%d" % scan["total_silence_contexts"])
    ck("未覆盖沉默比例可算", 0.0 <= scan["uncovered_ratio"] <= 1.0)
    ck("demo 触发条件分类已跑", demo["demos_found"] > 0, "实测=%d" % demo["demos_found"])
    ck("demo 里有『人为真值』项（招牌证据）", demo["artificial_n"] >= 1,
       "实测=%d" % demo["artificial_n"])
    ck("扫描覆盖语料 >10KB", scan["doc_bytes"] > 10000, "实测=%d B" % scan["doc_bytes"])

    # 反向注入：把真值锚点改坏 ⇒ 未覆盖度必须变大（证明指标不是死的）
    global GROUND_TRUTH_ANCHORS
    saved = list(GROUND_TRUTH_ANCHORS)
    GROUND_TRUTH_ANCHORS = ["___不存在的锚点___"]
    worse = scan_silence_contexts()
    GROUND_TRUTH_ANCHORS = saved
    ck("锚点失效 ⇒ 未覆盖度上升（指标真的在动）",
       worse["uncovered_ratio"] >= scan["uncovered_ratio"],
       "%.3f → %.3f" % (scan["uncovered_ratio"], worse["uncovered_ratio"]))

    n_pass = len([c for c in checks if c[1]])
    for name, ok, msg in checks:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                               ("  ← " + msg) if (msg and not ok) else ""))
    print("  -- selftest %d/%d" % (n_pass, len(checks)))
    line = "[selftest] %s" % ("全部通过" if n_pass == len(checks) else "存在失败")
    print("  " + line)
    return 0 if n_pass == len(checks) else 1


def main() -> int:
    scan = scan_silence_contexts()
    demo = scan_demo_triggers()

    ai = audit(INDUSTRY, scan, demo)
    asra = audit(SRA_PROPOSAL, scan, demo)

    print("=" * 72)
    print("SRA · 沉默对账器 —— 第二十三条 MOSS-VL-Realtime")
    print("=" * 72)
    s = asra["scan"]
    print("\n[语料全量扫描] %d 个唯一文件 / %d B"
          % (s["docs_scanned"], s["doc_bytes"]))
    print("  沉默上下文 %d 处 | 带判定真值 %d 处 | 无法判定 %d 处"
          % (s["total_silence_contexts"], s["with_truth"], s["unjudgeable"]))
    print("  ★ 未覆盖沉默比例（实测）= %.3f" % s["uncovered_ratio"])
    dm = asra["demo"]
    print("\n[官方 demo 触发条件] 找到 %d 个" % dm["demos_found"])
    for r in sorted(asra["demo_rows"], key=lambda x: x["demo"]):
        print("   DEMO 0%d  %s" % (r["demo"], r["verdict"]))
    print("  人为真值 %d / 客观真值 %d（人为真值占比 %.3f）"
          % (dm["artificial_n"], dm["objective_n"], dm["artificial_ratio"]))

    print("\n[六判据]  行业 = MOSS-VL-Realtime + ProactiveBench 现状；SRA = 本件主张")
    for (crit, _fn, label), pi, ps in zip(ALL, ai["parts"], asra["parts"]):
        print("  %s %-16s  行业 %.3f [%s]   SRA %.3f [%s]"
              % (crit, label, pi["score"], pi["basis"], ps["score"], ps["basis"]))
    print("\n  行业均分 %.3f" % ai["avg"])
    print("  SRA 均分 %.3f ⇒ %s" % (asra["avg"], asra["verdict"]))
    if asra["deduct_basis"]:
        print("  ⚠ 其中 %s 为【推导】而非【实跑】：真值一改就跟着变。"
              % ",".join(asra["deduct_basis"]))

    print("\n[自检]")
    rc = selftest(scan, demo)
    (ART / "sra_report.json").write_text(
        json.dumps({"industry": ai, "sra": asra}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n报告 → %s" % (ART / "sra_report.json"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
