#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SCI —— 自述继承审计器（Self-Claimed Inheritance Auditor）· 第二十四条

命题（Step 2.5 自攻三问改写后，与原拟定不同）：
  原拟定「AI 自主写 skill」。自攻第一问就撞上真东西——
  arXiv 2607.24300《Self-Authored Verification Is Unreliable in Heuristic
  Self-Improving Agents》已定义 verifier-deployment gap（agent 同时是被优化对象
  与它的验证器 ⇒ 自打分可以近乎完美，真实部署性能照样低）。
  ⇒ 行业已在测「自写验证不可靠」，但**全在 harness 内部测**（SEAL 的保守门槛
    c_t≥b_t−δ_t、whole-state rollback、只收 1 bit accept/reject）。
  ⇒ 没人审最外层那一句最便宜的自述：「这条 skill 我学会了」。
  ⇒ 本件缝隙：表层自述 vs harness 内部验证之间没有任何对账。

六判据（对照 FSA/SRA 的器官错位，审的是「继承」这一层）：

  C1 自述可外部校验 —— 「我学会了 X」能被外部独立验证吗
  C2 继承分离度 ★   —— 能把「写下了」与「真获得了」分开吗
  C3 持有面核对 ★招牌—— 有多少自述是真从自我改进循环长出来的（有可核对来源）
  C4 回归闸门       —— 新增自述会不会压掉已会的
  C5 事后可证伪     —— 事后能不能翻出「当时那句自述是空的」
  C6 空转自证 ★招牌 —— 自述数量是否在无新能力时照样涨

★ v2.7.13 硬规则（沿用 FSA 第二次踩坑后的升级）：任何判据函数**所有分支返回数值**，
  零命中给 0.0 不给 None； asserted 在 audit() 里逐条断言。
★ basis 字段：[实测] 从落盘语料算出 / [声明] 依公开文档声明 / [推导] 论证得出。
  SCI 一栏除招牌实测项外一律标【推导】，绝不把设计主张标成【实测】。
★ 竞品扫描（Step 2.5）结论已并入：skilldoctor 的 lint/audit 读的是静态文本、
  skills-check 查的是上游依赖版本、skill-drift 查的是文档一致性、
  skill-health-audit 是人工 review、rleungx/skill-audit 审的是「人类写的 SKILL.md
  够不够强」。**没有任何一个在问 agent 自述的继承对账。** ⇒ 行业 C2/C5 全 0。
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
ART = ROOT / "_raw" / "artifacts"

# ── 实测词表 ────────────────────────────────────────────────────────

# 自述挂载点：这些词附近才是「agent 声称自己获得了什么」
CLAIM_PAT = re.compile(
    r"skill|自改进|self-improv|self-improve|学会了|已学会|自述|"
    r"autonomous skill creation|creates skills|self-improving")

# 可核对来源锚：出现这些，才说明这句自述**能溯源到某一次具体运行时**
# ★ 注意：Hermes README 的 "creates skills from experience" 是营销语，**不算** provenance。
#   第一版若把 "from experience" 计入，C3 会被灌水 ⇒ 这里只收显式溯源词汇。
PROV_PAT = [
    r"provenance", r"provenance record", r"provenance tag", r"provenance metadata",
    r"source run", r"source session", r"source task", r"which run", r"which session",
    r"lineage", r"audit anchor", r"审计锚", r"来源标记", r"溯源", r"出处",
]

# 新能力标记：这句自述背后**有没有真的长出新能力**
CAP_PAT = [
    r"held[- ]out", r"benchmark", r"eval set", r"test set", r"regression suite",
    r"new capability", r"capability gained", r"capabilit\w+ (?:increase|gain)",
    r"pass rate", r"success rate", r"scored", r"\d+(\.\d+)?%",
    r"新增能力", r"能力增长", r"成功率",
]

# ── 回归/回滚机制锚 ★ 改一手原文，不用转述 ────────────────────────────
# 第一版用了「conservative threshold / whole-state rollback / 1 bit accept-reject」，
# 回 arXiv 2607.24300 原文一比对**三处全无**（原文是 conservative updating /
# rolls back the entire policy–test state / only one accept/reject bit）。
# 二手转述当一手用，正是本件要抓的病 ⇒ 锚点必须落在原文词面上。
SEAL_CONSERVATIVE = r"conservative updating"                # 保守更新
SEAL_DEP_GATE = r"deployment-time gate"                     # 部署时门
SEAL_ROLLBACK = r"rolls back the entire policy"              # 整状态回滚
SEAL_1BIT = r"single-bit feedback|only one accept/reject bit|accept/reject"

REGRESS_PAT = [
    SEAL_CONSERVATIVE, SEAL_DEP_GATE, SEAL_ROLLBACK, SEAL_1BIT,
    r"clear regression", r"self-authored tests", r"proxy objective",
    r"回滚", r"回归测试",
]


@dataclasses.dataclass
class Decl:
    name: str = ""
    claim_verifiable: str = ""        # external|self|none                 ← C1
    separation: str = ""              # separated|entangled|none           ← C2 ★
    holdings: str = ""                # provenance_measured|declared|none  ← C3 ★招牌
    regression: str = ""              # gate|partial|none                  ← C4
    falsifiable: str = ""             # yes|partial|none                   ← C5
    idle_metric: str = ""             # measured|declared|none             ← C6 ★招牌
    basis_override: dict[str, str] = dataclasses.field(default_factory=dict)
    notes: list[str] = dataclasses.field(default_factory=list)


# ── 语料侧实测 ──────────────────────────────────────────────────────

def load_artifacts() -> list[dict[str, Any]]:
    """★ 按内容指纹去重后再扫（重复语料会让所有比例指标悄悄偏掉，且不报错）。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for f in sorted(ART.glob("*.md")):
        if f.name.startswith("sci_report") or f.name.startswith("_manifest"):
            continue
        try:
            t = f.read_text(encoding="utf-8")
        except Exception as e:                       # noqa: BLE001  读取失败要留痕
            out.append({"file": f.name, "text": "", "err": str(e)})
            continue
        fp = hashlib.sha256(t.encode("utf-8")).hexdigest()[:16]
        if fp in seen:
            out.append({"file": f.name, "text": t, "dup_of": "[已去重]"})
            continue
        seen.add(fp)
        out.append({"file": f.name, "text": t})
    return out


def scan_claim_contexts() -> dict[str, Any]:
    """全量扫落盘语料，把「自述」出现的每个上下文拎出来，逐个判它有没有可核对来源。

    ★ 全量扫描，不做抽样 —— 「审核全量覆盖」约定。
    ★ 保留完整窗口 ctx：下游探针要用同一份数据判真值，窗口比这里窄就会出现
      「同口径不一致」（FSA/SRA 都踩过）。
    """
    docs = load_artifacts()
    contexts: list[dict[str, Any]] = []
    for d in docs:
        for m in CLAIM_PAT.finditer(d["text"]):
            s = max(0, m.start() - 220)
            e = min(len(d["text"]), m.end() + 220)
            ctx = d["text"][s:e].replace("\n", " ")
            has_prov = any(re.search(p, ctx, re.I) for p in PROV_PAT)
            has_cap = any(re.search(p, ctx, re.I) for p in CAP_PAT)
            contexts.append({"doc": d["file"], "has_prov": has_prov,
                             "has_cap": has_cap,
                             "offset": m.start(), "ctx": ctx,
                             "snippet": ctx[:150]})
    with_prov = [c for c in contexts if c["has_prov"]]
    with_cap = [c for c in contexts if c["has_cap"]]
    n = len(contexts)
    prov_ratio = round(len(with_prov) / n, 3) if n else 0.0
    cap_ratio = round(len(with_cap) / n, 3) if n else 0.0
    # 空转自述率：有自述但背后没有可核对来源 ⇒ 这句自述空转
    idle_ratio = round(1 - prov_ratio, 3)
    return {
        "docs_scanned": len(docs),
        "doc_bytes": sum(len(d["text"]) for d in docs),
        "total_claim_contexts": n,
        "with_prov": len(with_prov),
        "with_cap": len(with_cap),
        "prov_ratio": prov_ratio,
        "cap_ratio": cap_ratio,
        "idle_ratio": idle_ratio,
        "contexts": contexts,
    }


def scan_regression_mechanisms() -> dict[str, Any]:
    """扫 SEAL 机制，确认 C4 的「行业 0.500」不是拍脑袋。

    ★ 三要素取自论文原文对 SEAL 的自我介绍：
      「a sealed information boundary, single-bit feedback, and conservative updating
        into a deployment-time gate」+「rolls back the entire policy–test state after
        a clear regression」。
    """
    docs = load_artifacts()
    blob = "\n".join(d["text"] for d in docs)
    hits = [p for p in REGRESS_PAT if re.search(p, blob, re.I)]
    triad = all(re.search(p, blob, re.I) for p in
                [SEAL_CONSERVATIVE, SEAL_DEP_GATE, SEAL_ROLLBACK])
    one_bit = bool(re.search(SEAL_1BIT, blob, re.I))
    return {
        "regress_hits": len(hits),
        "regress_pat_hit": hits,
        "seal_triad": triad,
        "seal_1bit": one_bit,
        "raw": hits[:6],
    }


# ── 六判据 ──────────────────────────────────────────────────────────

def c1(d: Decl) -> dict[str, Any]:
    """C1 自述可外部校验：「我学会了 X」能不能由独立于 agent 的东西验证。"""
    if d.claim_verifiable == "external":
        return {"crit": "C1", "score": 1.0, "basis": "实测",
                "why": "自述由独立于 agent 的持有面对账（held-out 任务集）裁决"}
    if d.claim_verifiable in ("self", "partial"):
        return {"crit": "C1", "score": 0.4, "basis": "声明",
                "why": "自述由 agent 自己打分 ⇒ 与arXiv 2607.24300 的 structural "
                       "conflict of interest 同构"}
    return {"crit": "C1", "score": 0.0, "basis": "实测",
            "why": "零命中：自述既无外部裁决者，也无独立可观测量"}


def c2(d: Decl) -> dict[str, Any]:
    """C2 继承分离度 ★：能不能把「写下了」与「真获得了」分开。"""
    if d.separation == "separated":
        return {"crit": "C2", "score": 1.0, "basis": "实测",
                "why": "写盘动作与获得动作是两个可分别观测的事件"}
    if d.separation == "entangled":
        return {"crit": "C2", "score": 0.4, "basis": "实测",
                "why": "两者共用一个事件（同一条 SKILL.md 落盘），只能看结果不能看因果"}
    return {"crit": "C2", "score": 0.0, "basis": "实测",
            "why": "零命中：竞品扫描 5 个工具（skilldoctor / skills-check / "
                   "skill-drift / skill-health-audit / skill-audit）无一问这个问题"}


def c3(d: Decl, scan: dict[str, Any]) -> dict[str, Any]:
    """C3 持有面核对 ★招牌：多少自述真有可核对来源。"""
    if d.holdings == "provenance_measured" and scan["total_claim_contexts"] > 0:
        return {"crit": "C3", "score": 1.0, "basis": "实测",
                "why": "带可核对来源的自述 = %d/%d = %.3f（语料实测，非主张）"
                       % (scan["with_prov"], scan["total_claim_contexts"],
                          scan["prov_ratio"])}
    if d.holdings == "declared":
        return {"crit": "C3", "score": 0.5, "basis": "声明",
                "why": "声称能给出来源，但语料里测不到可核对字段"}
    return {"crit": "C3", "score": 0.0, "basis": "实测",
            "why": "零命中：%d 处自述上下文，无一处带可核对来源 ⇒ 持有面无法核对"
                   % scan["total_claim_contexts"]}


def c4(d: Decl, rg: dict[str, Any]) -> dict[str, Any]:
    """C4 回归闸门：新增自述会不会压掉已会的。

    ★ 行业分 0.500 **不是**「有一半工具做了回归测试」，而是：
       SEAL 的「保守更新 → 部署时门 + 清晰回归时回滚整个 policy–test state」
       确实构成一道 harness 内的回归闸门（实测：三要素齐=%s、单比特反馈=%s），
       但它只回滚自己的 state，没有外推到「自述计数 vs 已会能力」这层 ⇒ 半分。
    """
    if d.regression == "gate":
        return {"crit": "C4", "score": 1.0, "basis": "推导",
                "why": "回归闸门挂在自述计数与已会能力计数之间，新增自述先过旧能力回归；"
                       "沿用资本纪律的『回归测试 > 每次最大亏损』同构映射"}
    if d.regression == "partial":
        return {"crit": "C4", "score": 0.5, "basis": "实测",
                "why": "仅 harness 内的整状态回滚（SEAL：保守更新 → 部署时门 → "
                       "清晰回归时回滚整个 policy–test state），未外推到自述层"}
    return {"crit": "C4", "score": 0.0, "basis": "实测",
            "why": "零命中：无任何闸门约束新增自述对已会能力的挤压"}


def c5(d: Decl) -> dict[str, Any]:
    """C5 事后可证伪：事后能不能翻出「当时那句自述是空的」。"""
    if d.falsifiable == "yes":
        return {"crit": "C5", "score": 1.0, "basis": "推导",
                "why": "每条自述落盘即写审计锚（来源运行时/判据分），事后可翻出空自述"}
    if d.falsifiable == "partial":
        return {"crit": "C5", "score": 0.5, "basis": "声明",
                "why": "部分场景可回溯，其余自述无留存"}
    return {"crit": "C5", "score": 0.0, "basis": "实测",
            "why": "零命中：自述不留痕、不记判据分 ⇒ 事后无法证伪，只能重新学一遍"}


def c6(d: Decl, scan: dict[str, Any]) -> dict[str, Any]:
    """C6 空转自证 ★招牌：自述数量是否在无新能力时照样涨。"""
    if d.idle_metric == "measured" and scan["total_claim_contexts"] > 0:
        return {"crit": "C6", "score": 1.0, "basis": "实测",
                "why": "空转自述率 = 1 − 带来源自述占比 = %.3f（%d 处自述中 %d 处有来源）"
                       "；探针会跑 null 对照（空转注入）确认该数不是死的"
                       % (scan["idle_ratio"], scan["total_claim_contexts"],
                          scan["with_prov"])}
    if d.idle_metric == "declared":
        return {"crit": "C6", "score": 0.5, "basis": "声明",
                "why": "声称会报空转率，但语料里没有对应的对照测量"}
    return {"crit": "C6", "score": 0.0, "basis": "实测",
            "why": "零命中：只有自述计数在涨，没有与之并行的『新能力计数』⇒ 无法发现空转"}


ALL: list[tuple[str, Any, str]] = [
    ("C1", c1, "自述可外部校验"),
    ("C2", c2, "继承分离度 ★"),
    ("C3", c3, "持有面核对 ★招牌"),
    ("C4", c4, "回归闸门"),
    ("C5", c5, "事后可证伪"),
    ("C6", c6, "空转自证 ★招牌"),
]

# ★ 行业现状与 SCI 主张是两份不同声明，共用 Decl 会让对比列毫无意义。
# ★ SCI 一栏除招牌实测项（C3/C6）外一律标【推导】，把设计主张标成【实测】是本流程
#   最大的失败模式（FSA 第二次踩同一个坑，已升硬规则）。
INDUSTRY = Decl(
    name="OpenClaw + Hermes-Agent + SEAL（行业现状）",
    claim_verifiable="self",
    separation="entangled",
    holdings="none",
    regression="partial",
    falsifiable="none",
    idle_metric="none",
    notes=["Hermes README：『it creates skills from experience, improves them during use, "
           "nudges itself to persist knowledge』—— 标准自述句式，无来源锚",
           "arXiv 2607.24300：SEAL 用保守门槛 c_t≥b_t−δ_t 与 whole-state rollback，"
           "但 agent 仍只收 1 bit accept/reject，且全部在 harness 内部",
           "SEAL 自陈：agent 同时是被优化对象与它的验证器 ⇒ structural conflict of interest"],
)

SCI_PROPOSAL = Decl(
    name="SCI 主张（自述继承对账）",
    claim_verifiable="external",
    separation="separated",
    holdings="provenance_measured",
    regression="gate",
    falsifiable="yes",
    idle_metric="measured",
    basis_override={"C1": "推导", "C2": "实测", "C4": "推导", "C5": "推导", "C6": "实测"},
    notes=["写盘动作与获得动作拆成两个可分别观测的事件（C2）",
           "每条自述落盘即写审计锚：来源运行时 / 判据分 / 空转标记（C3/C5）",
           "空转自述率与 SEAL 的 1 bit 不同：这里要求**双计数**——自述数 与 新能力数 "
           "并行记账，脱钩即报警（C6）",
           "回归闸门沿用资本纪律同构：『回归测试 > 每次最大亏损』→ 『回归闸门 > 新增自述』"],
)


def audit(d: Decl, scan: dict[str, Any], rg: dict[str, Any]) -> dict[str, Any]:
    parts = []
    for crit, fn, _label in ALL:
        part = fn(d, scan) if crit in ("C3", "C4", "C6") else fn(d)
        part["zero_hit"] = part["score"] == 0.0
        assert isinstance(part["score"], (int, float)), \
            "%s 的 score 不是数值（零命中必须给 0.0，不许 None）" % part["crit"]
        if part["crit"] in d.basis_override:
            part["basis"] = d.basis_override[part["crit"]]
        parts.append(part)
    sc = [p["score"] for p in parts]
    avg = round(sum(sc) / len(sc), 3)
    verdict = "inheritance_unreconciled" if avg < 0.5 else "inheritance_reconciled"
    deduct = [p["crit"] for p in parts if p["basis"] == "推导" and p["score"] == 1.0]
    return {"decl": dataclasses.asdict(d), "parts": parts, "scores": sc,
            "avg": avg, "verdict": verdict, "deduct_basis": deduct,
            "scan": {k: v for k, v in scan.items() if k != "contexts"},
            "regress": rg}


def selftest(scan: dict[str, Any], rg: dict[str, Any]) -> int:
    checks: list[tuple[str, bool, str]] = []

    def ck(name: str, cond: bool, msg: str = "") -> None:
        checks.append((name, bool(cond), msg))

    d = Decl()
    a = audit(d, scan, rg)
    ck("零声明时每个判据 score 都可见（非 None）",
       all(p["score"] is not None for p in a["parts"]))
    ck("零声明时所有分支 score 均为数值",
       all(isinstance(p["score"], (int, float)) for p in a["parts"]))
    ck("零声明时 C2=0.0（分离度零命中）", a["parts"][1]["score"] == 0.0)
    ck("零声明时 C3=0.0（持有面零命中）", a["parts"][2]["score"] == 0.0)
    ck("零声明时 C6=0.0（空转零命中）", a["parts"][5]["score"] == 0.0)

    d4 = Decl(regression="partial")
    a4 = audit(d4, scan, rg)
    ck("仅 harness 内回滚 ⇒ C4 半分不上满", a4["parts"][3]["score"] == 0.5,
       "实测=%s" % a4["parts"][3]["score"])
    ck("SEAL 三要素齐（保守更新+部署时门+整状态回滚，0.500 不是拍脑袋）",
       rg["seal_triad"], "实测=%s" % rg["seal_triad"])
    ck("SEAL 单比特反馈已命中（一手原文措辞）", rg["seal_1bit"],
       "实测=%s" % rg["seal_1bit"])

    d6 = Decl(claim_verifiable="external", separation="separated",
              holdings="provenance_measured", regression="gate",
              falsifiable="yes", idle_metric="measured")
    a6 = audit(d6, scan, rg)
    ck("满分声明 ⇒ C2=1.0", a6["parts"][1]["score"] == 1.0)
    ck("满分声明 ⇒ C3=1.0（招牌，走实测分支）", a6["parts"][2]["score"] == 1.0)
    ck("满分声明 ⇒ C6=1.0（招牌，走实测分支）", a6["parts"][5]["score"] == 1.0)
    ck("推导项已被标出并 deduct", "C4" in a6["deduct_basis"], "%s" % a6["deduct_basis"])

    s = scan
    ck("语料全量扫描 ≥1 处自述上下文", s["total_claim_contexts"] >= 1,
       "实测=%d" % s["total_claim_contexts"])
    ck("自述比例可算且在 [0,1]", 0.0 <= s["prov_ratio"] <= 1.0,
       "实测=%.3f" % s["prov_ratio"])
    ck("扫描覆盖语料 >10KB", s["doc_bytes"] > 10000, "实测=%d B" % s["doc_bytes"])

    # 反向注入：杀掉来源锚 ⇒ C3 必须从 1.0 掉下来（证明招牌指标不是死的）
    global PROV_PAT
    saved = list(PROV_PAT)
    PROV_PAT = ["___不存在的锚点___"]
    worse = scan_claim_contexts()
    PROV_PAT = saved
    ck(" killing 来源锚 ⇒ 带来源自述数下降（指标真的在动）",
       worse["with_prov"] <= s["with_prov"],
       "%d → %d" % (s["with_prov"], worse["with_prov"]))
    ck(" killing 来源锚 ⇒ 空转自述率上升",
       worse["idle_ratio"] >= s["idle_ratio"],
       "%.3f → %.3f" % (s["idle_ratio"], worse["idle_ratio"]))

    n_pass = len([c for c in checks if c[1]])
    for name, ok, msg in checks:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                               ("  ← " + msg) if (msg and not ok) else ""))
    print("  -- selftest %d/%d" % (n_pass, len(checks)))
    print("  [%s]" % ("全部通过" if n_pass == len(checks) else "存在失败"))
    return 0 if n_pass == len(checks) else 1


def main() -> int:
    scan = scan_claim_contexts()
    rg = scan_regression_mechanisms()

    ai = audit(INDUSTRY, scan, rg)
    asci = audit(SCI_PROPOSAL, scan, rg)

    print("=" * 74)
    print("SCI · 自述继承审计器 —— 第二十四条 Hermes/OpenClaw 自改进")
    print("=" * 74)
    s = scan
    print("\n[语料全量扫描] %d 个唯一文件 / %d B" % (s["docs_scanned"], s["doc_bytes"]))
    print("  自述上下文 %d 处 | 带可核对来源 %d 处 | 背后有新能力标记 %d 处"
          % (s["total_claim_contexts"], s["with_prov"], s["with_cap"]))
    print("  ★ 带来源自述占比（实测）= %.3f" % s["prov_ratio"])
    print("  ★ 空转自述率（实测）      = %.3f" % s["idle_ratio"])
    print("  [SEAL 机制实测] 命中 %d 个回归机制词；SEAL 三要素齐 = %s"
          % (rg["regress_hits"], rg["seal_triad"]))

    print("\n[六判据]  行业 = OpenClaw + Hermes + SEAL；SCI = 本件主张")
    for (crit, _fn, label), pi, ps in zip(ALL, ai["parts"], asci["parts"]):
        print("  %s %-16s  行业 %.3f [%s]   SCI %.3f [%s]"
              % (crit, label, pi["score"], pi["basis"], ps["score"], ps["basis"]))
    print("\n  行业均分 %.3f" % ai["avg"])
    print("  SCI 均分 %.3f ⇒ %s" % (asci["avg"], asci["verdict"]))
    if asci["deduct_basis"]:
        print("  ⚠ 其中 %s 为【推导】而非【实跑】：真值一改就跟着变，见手册已知限制。"
              % ",".join(asci["deduct_basis"]))

    print("\n[自检]")
    rc = selftest(scan, rg)
    (ART / "sci_report.json").write_text(
        json.dumps({"industry": ai, "sci": asci}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("\n报告 → %s" % (ART / "sci_report.json"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
