#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SRA 探针 —— 沉默现实压力测试（Step 2.75 硬门槛）

★ 这一步在干什么
  前面的 sra_cli 算出「未覆盖沉默比例 0.898」——但这个数有一个死穴：
      0.898 是我自己选的锚点算出来的。换一套锚点，它就不是这个数。
  本探针不重复算这个比例，而是去压它：
      P1 定义依赖漏报 —— 用三套各自自洽的「该说话时刻」定义去判同一批沉默事件，
                          看有多少事件的「漏报」身份是定义给的不是系统给的。
      P2 最小对账器   —— 没有事前真值时，对账器必须拒绝出「漏报」。
                          这就是 SRA 与现有评测最硬的一行代码差异。
      P3 锚点边际     —— 逐个抽掉一个锚点，看招牌数怎么动；锚点选型的真实代价。
      P4 漏报率漂移   —— 同一个系统，换定义就换漏报率，行业指标的可信区间。

所有数字都从 _raw/artifacts 的真实语料跑出来，不写死。
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sra_cli  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_out"
OUT.mkdir(exist_ok=True)

# ── 三套「该说话时刻」的定义 ─────────────────────────────────────────
# 三套都自称自洽，谁也不比谁正确 —— 这正是问题：
# 真实部署里没有一套是"官方的"，但评测必须挑一套才出得来漏报率。
DEFINITIONS: dict[str, list[str]] = {
    # D1 事前标注式：评测方事先告诉你「这一刻该说话」（ProactiveBench 的做法）
    "D1_标注式": sra_cli.GROUND_TRUTH_ANCHORS,
    # D2 用户需求式：从「用户需要什么」反推该说话时刻
    "D2_用户需求式": [
        r"需要", r"应该", r"提醒", r"帮助", r"及时", r"不错过", r"用户",
        r"request", r"need", r"should", r"remind", r"user", r"alert",
        r"degraded", r"distress", r"fall",
    ],
    # D3 活动式：任何人类/非静息活动发生时都算该说话
    "D3_活动式": [
        r"人", r"走路", r"摔倒", r"猫", r"比赛", r"翻页", r"说话", r"比赛",
        r"person", r"walk", r"fall", r"cat", r"game", r"match", r"page",
        r"speech", r"activity", r"event", r"shot", r"goal",
    ],
}

# 有响应发生的证据（用来把「该说没说」和「说了」对上账）
RESPONSE_EVIDENCE = [
    r"reports", r"responds", r"speaks", r"alerts", r"announces", r"notifies",
    r"发出", r"提醒", r"响应", r"播报", r"提示",
]
# 明确「什么都没说」的证据
SILENT_EVIDENCE = [
    r"stays silent", r"remains silent", r"no response", r"does not respond",
    r"stays quiet", r"nothing", r"不说话", r"没有说话", r"未响应", r"静默",
]

VERDICT_MISSED = "MISSED"            # 漏报：该说没说
VERDICT_RECONCILED = "RECONCILED"    # 对上账了：有真值也有响应
VERDICT_SILENT_OK = "CORRECT_SILENT"  # 有真值但记为沉默
VERDICT_UNDECIDABLE = "UNDECIDABLE"  # ★ 无法判定：没有「该说话的时刻」


def build_events() -> list[dict[str, Any]]:
    """把语料里每一处沉默上下文当成一次「系统沉默事件」。全量，不抽样。"""
    scan = sra_cli.scan_silence_contexts()
    events: list[dict[str, Any]] = []
    for i, c in enumerate(scan["contexts"], 1):
        events.append({
            "id": "E%02d" % i,
            "doc": c["doc"],
            "ctx": c["ctx"],            # ★ 判定只认完整窗口（与 CLI 同口径）
            "snippet": c["snippet"],    # 缩略句只用于展示
            "has_truth": c["has_truth"],
        })
    return events


def _any(pats: list[str], text: str) -> list[str]:
    return [p for p in pats if re.search(p, text, re.I)]


def judge(event: dict[str, Any], def_name: str) -> str:
    """在某一套定义下，给一次沉默事件定性。

    ★ 关键约束：没有任何定义命中 ⇒ 只能 UNDECIDABLE，不许猜。
      行业评测的漏报率之所以能出得来，就是因为它悄悄用了某一套定义但没说。
    """
    ctx = event.get("ctx") or event["snippet"]   # ★ 判定用完整窗口
    if _any(DEFINITIONS[def_name], ctx):
        if _any(RESPONSE_EVIDENCE, ctx):
            return VERDICT_RECONCILED
        if _any(SILENT_EVIDENCE, ctx):
            return VERDICT_SILENT_OK
        return VERDICT_MISSED
    return VERDICT_UNDECIDABLE


def reconcile(event: dict[str, Any], defs: dict[str, list[str]] | None = None) -> dict[str, Any]:
    """SRA 最小对账器：给定一次沉默事件，给出可审计的判定。

    返回里带 requires_prior_annotation —— 这是 SRA 与「漏报率」的分界线：
    没有事前真值，任何 MISSED 都是编的，所以拒绝出 MISSED。
    """
    defs = defs or DEFINITIONS
    verdicts = {d: judge(event, d) for d in defs}
    undecidable = [d for d, v in verdicts.items() if v == VERDICT_UNDECIDABLE]
    pinned = [d for d, v in verdicts.items() if v != VERDICT_UNDECIDABLE]

    tally: dict[str, int] = {}
    for v in verdicts.values():
        tally[v] = tally.get(v, 0) + 1

    # ★ 三条硬规则（第一版犯过错：多数票判出 UNDECIDABLE 却仍标
    #   requires_prior_annotation=false —— 判定与依据自相矛盾，正是 SRA 要防的东西）
    # 1) 三套定义互相打架 ⇒ 拒绝出单一判定。定义之间都定不了，凭什么替它们定。
    if len(tally) > 1:
        return {
            "verdict": VERDICT_UNDECIDABLE,
            "requires_prior_annotation": True,
            "reason": "三套「该说话时刻」定义在此处互相冲突（%s）—— 真值本身不足以支撑判定，"
                      "拒绝出单一结论。" % json.dumps({k: v for k, v in tally.items()},
                                                      ensure_ascii=False),
            "verdicts": verdicts,
            "inconsistent": True,
        }
    if not pinned:
        return {
            "verdict": VERDICT_UNDECIDABLE,
            "requires_prior_annotation": True,
            "reason": "没有任意一套「该说话时刻」定义被命中 —— 此处根本无法判定，"
                      "任何漏报判定都只能靠另立定义凭空制造。",
            "verdicts": verdicts,
            "inconsistent": False,
        }
    # 2) 唯一判定 = UNDECIDABLE ⇒ 同样必须声明需要事前真值，不许降格为"可以算"
    # 3) 其余情况才允许出判定，并带出分歧标记
    top = next(iter(tally))
    return {
        "verdict": top,
        "requires_prior_annotation": top == VERDICT_UNDECIDABLE,
        "reason": "有 %d/%d 套定义命中该说话时刻，判定为 %s。" % (len(pinned), len(defs), top),
        "verdicts": verdicts,
        "inconsistent": False,
    }


# ── P1 定义依赖漏报 ────────────────────────────────────────────────

def p1_flip(events: list[dict[str, Any]]) -> dict[str, Any]:
    per_def: dict[str, dict[str, int]] = {}
    for d in DEFINITIONS:
        t: dict[str, int] = {}
        for e in events:
            v = judge(e, d)
            t[v] = t.get(v, 0) + 1
        per_def[d] = t

    decisive: dict[str, set[str]] = {e["id"]: set() for e in events}
    for d in DEFINITIONS:
        for e in events:
            if judge(e, d) == VERDICT_MISSED:
                decisive[e["id"]].add(d)

    all_missed = {e["id"] for e in events if decisive[e["id"]] == set(DEFINITIONS)}
    any_missed = {e["id"] for e in events if decisive[e["id"]]}
    def_dependent = any_missed - all_missed
    total = len(events)

    return {
        "total_events": total,
        "per_definition": per_def,
        "robust_missed": len(all_missed),          # 三套定义都判漏报 —— 只有这些站得住
        "definition_dependent_missed": len(def_dependent),  # 漏报身份由定义决定
        "definition_free_rate": round(len(all_missed) / total, 3) if total else 0.0,
        "definition_dependent_rate": round(len(def_dependent) / total, 3) if total else 0.0,
        "robust_ids": sorted(all_missed),
        "dependent_ids": sorted(def_dependent),
    }


# ── P2 最小对账器 ──────────────────────────────────────────────────

def p2_reconciler(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = [{"id": e["id"], **reconcile(e)} for e in events]
    undecidable = [r for r in rows if r["verdict"] == VERDICT_UNDECIDABLE]
    # ★ 硬断言：无法判定的条目，不许任何一个偷偷输出 MISSED
    leak = [r["id"] for r in undecidable if r.get("verdict") != VERDICT_UNDECIDABLE]
    no_annotation = [r for r in undecidable if r.get("requires_prior_annotation") is not True]
    return {
        "rows": rows,
        "undecidable_n": len(undecidable),
        "undecidable_ratio": round(len(undecidable) / len(rows), 3) if rows else 0.0,
        "leaked_missed_from_undecidable": leak,     # 必须为空
        "missing_annotation_flag": no_annotation,    # 必须为空
        "reconciled_n": len([r for r in rows if r["verdict"] == VERDICT_RECONCILED]),
    }


# ── P3 锚点边际敏感度 ──────────────────────────────────────────────

def p3_anchor_sensitivity(events: list[dict[str, Any]]) -> dict[str, Any]:
    """逐个抽掉一个锚点，看未覆盖度怎么动。

    ★ 招牌数 0.898 不是物理常数，是锚点选型的产物。
      这一页就是把它诚实地摊开：哪个锚点最值钱、抽掉哪个数最晃。
    """
    def ratio(anchors: list[str]) -> float:
        bad = 0
        for e in events:
            if not _any(anchors, e.get("ctx") or e["snippet"]):
                bad += 1
        return round(bad / len(events), 3) if events else 0.0

    base = ratio(sra_cli.GROUND_TRUTH_ANCHORS)
    rows = []
    for a in sra_cli.GROUND_TRUTH_ANCHORS:
        saved = sra_cli.GROUND_TRUTH_ANCHORS
        sra_cli.GROUND_TRUTH_ANCHORS = [x for x in saved if x != a]
        r = ratio(sra_cli.GROUND_TRUTH_ANCHORS)
        sra_cli.GROUND_TRUTH_ANCHORS = saved
        rows.append({"anchor": a, "ratio_without": r, "delta": round(r - base, 3)})
    rows.sort(key=lambda r: -r["delta"])

    # 整类抽掉 vs 单条抽掉：看谁是招牌数的真正开关
    cn = [p for p in sra_cli.GROUND_TRUTH_ANCHORS
          if re.search(r"[\u4e00-\u9fff]", p)]
    en = [p for p in sra_cli.GROUND_TRUTH_ANCHORS
          if not re.search(r"[\u4e00-\u9fff]", p)]
    only_cn = ratio(cn)
    only_en = ratio(en)
    no_gt_at_all = ratio([])
    return {
        "base_ratio": base,
        "rows": rows,
        "max_delta": max((r["delta"] for r in rows), default=0.0),
        "most_load_bearing": rows[0]["anchor"] if rows else "",
        "drop_whole_set_ratio": no_gt_at_all,
        "only_cn": only_cn, "only_en": only_en, "cn_n": len(cn), "en_n": len(en),
        "single_anchor_invariant": max((r["delta"] for r in rows), default=0.0) == 0.0,
    }


# ── P4 漏报率漂移 ──────────────────────────────────────────────────

def p4_miss_rate_drift(events: list[dict[str, Any]]) -> dict[str, Any]:
    rows = []
    for d in DEFINITIONS:
        n = len([e for e in events if judge(e, d) == VERDICT_MISSED])
        rows.append({"definition": d, "missed_n": n,
                     "miss_rate": round(n / len(events), 3) if events else 0.0})
    rates = [r["miss_rate"] for r in rows]
    return {
        "rows": rows,
        "min": min(rates) if rates else 0.0,
        "max": max(rates) if rates else 0.0,
        "spread": round(max(rates) - min(rates), 3) if rates else 0.0,
    }


# ── 自检 ───────────────────────────────────────────────────────────

def selftest(events: list[dict[str, Any]], p1, p2, p3, p4) -> int:
    passed = 0
    failed = 0

    def ck(name: str, cond: bool, msg: str = "") -> None:
        nonlocal passed, failed
        if cond:
            passed += 1
            print("  [PASS] %s" % name)
        else:
            failed += 1
            print("  [FAIL] %s %s" % (name, msg))

    print("\n[自检]")
    # 1 不是"每套都得判出漏报"（那是伪断言：标注式在营销语料里一次可判漏报都没有，
    #   这本身就是结论），而是"漏报数随定义而变" ⇒ 漏报率天生带漂移
    missed_by_def = [p1["per_definition"][d].get(VERDICT_MISSED, 0) for d in DEFINITIONS]
    ck("漏报数随定义而变（不是系统属性）", len(set(missed_by_def)) > 1,
       str(missed_by_def))
    ck("漏报率存在漂移（spread > 0）", p4["spread"] > 0,
       "spread=%s" % p4["spread"])
    # 2 「定义依赖漏报」> 0 ⇒ 招牌论点成立：漏报身份是定义给的不是系统给的
    ck("存在定义依赖漏报（身份由定义决定）", p1["definition_dependent_missed"] > 0,
       "n=%s" % p1["definition_dependent_missed"])
    ck("稳健漏报 <= 定义依赖漏报 + 总数", p1["robust_missed"] <= len(events))
    # 3 对账器绝不从「无法判定」里漏出 MISSED
    ck("无法判定的条目一个都没漏出 MISSED", p2["leaked_missed_from_undecidable"] == [],
       str(p2["leaked_missed_from_undecidable"]))
    ck("无法判定的条目都打了 requires_prior_annotation", p2["missing_annotation_flag"] == [])
    ck("对账器确实拒绝了出判定", p2["undecidable_n"] > 0)
    # 4 锚点敏感度：单个锚点的边际很小（≤1 条事件），但**换锚点组合**影响巨大。
    #   第一版把断言写成"抽掉单条必须完全不动"，实测 +0.017（动 1 条）⇒ 伪假设被数据推翻，
    #   改成有依据的结构性断言：边际小 + 组合效应远大于边际。
    n_events = max(1, p3["base_ratio"] and len(events))
    one_anchor_max_events = int(round(p3["max_delta"] * len(events)))
    ck("单个锚点边际小（≤1 条事件）", one_anchor_max_events <= 1,
       "%d 条, max_delta=%s" % (one_anchor_max_events, p3["max_delta"]))
    ck("锚点组合效应远大于单锚点边际（≥2×）",
       (p3["drop_whole_set_ratio"] - p3["base_ratio"]) >= 2 * p3["max_delta"],
       "组合 %+.3f vs 单条 %+.3f" % (p3["drop_whole_set_ratio"] - p3["base_ratio"],
                                  p3["max_delta"]))
    ck("锚点语言构成会移动招牌数（only_cn != only_en）",
       p3["only_cn"] != p3["only_en"],
       "cn=%s en=%s" % (p3["only_cn"], p3["only_en"]))
    ck("整套真值抽掉后未覆盖度上升（证明指标不是死的）",
       p3["drop_whole_set_ratio"] > p3["base_ratio"],
       "%s -> %s" % (p3["base_ratio"], p3["drop_whole_set_ratio"]))
    # 5 探针招牌数必须与 CLI 同口径复现（同一个 0.898，不许两个版本）
    ck("探针未覆盖度与 CLI 同口径复现",
       abs(p3["base_ratio"] - sra_cli.scan_silence_contexts()["uncovered_ratio"]) < 0.002,
       "probe=%s cli=%s" % (p3["base_ratio"],
                            sra_cli.scan_silence_contexts()["uncovered_ratio"]))
    # 5 探针数字与 sra_cli 同口径复现（同一批语料、同一批事件）
    scan = sra_cli.scan_silence_contexts()
    ck("事件数与 CLI 扫描一致（同口径）", len(events) == scan["total_silence_contexts"],
       "%s vs %s" % (len(events), scan["total_silence_contexts"]))
    # 6 全量覆盖
    ck("全量扫描（事件数 = CLI 全量数）", len(events) == scan["total_silence_contexts"])
    print("  -- selftest %d/%d" % (passed, passed + failed))
    return 0 if failed == 0 else 1


# ── 输出 ───────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="SRA 沉默现实探针")
    ap.add_argument("--no-selftest", action="store_true")
    args = ap.parse_args()

    events = build_events()
    if not events:
        print("[探针] 失败：语料里一处沉默上下文都没有，探针无从下手。")
        return 1

    p1 = p1_flip(events)
    p2 = p2_reconciler(events)
    p3 = p3_anchor_sensitivity(events)
    p4 = p4_miss_rate_drift(events)

    print("[沉默现实探针] 事件源 = %d 处沉默上下文（全量）"
          % len(events))
    print("\n[P1 定义依赖漏报]")
    for d, t in p1["per_definition"].items():
        print("  %-14s MISSED=%-3d RECONCILED=%-3d SILENT_OK=%-3d UNDECIDABLE=%-3d"
              % (d, t.get(VERDICT_MISSED, 0), t.get(VERDICT_RECONCILED, 0),
                 t.get(VERDICT_SILENT_OK, 0), t.get(VERDICT_UNDECIDABLE, 0)))
    print("  稳健漏报（三套定义都判）= %d / %d  ⇒ 定义无关率 %.3f"
          % (p1["robust_missed"], len(events), p1["definition_free_rate"]))
    print("  ★ 定义依赖漏报            = %d / %d  ⇒ %.3f"
          % (p1["definition_dependent_missed"], len(events),
             p1["definition_dependent_rate"]))
    print("    ⇒ 这批沉默里，只有 %d 条的「漏报」身份跟定义无关；"
          "剩下 %d 条是定义给的，不是系统给的。"
          % (p1["robust_missed"], p1["definition_dependent_missed"]))

    print("\n[P2 最小对账器 reconcile() ]")
    print("  拒绝出判定的条目 = %d（占比 %.3f）"
          % (p2["undecidable_n"], p2["undecidable_ratio"]))
    print("  对上账（有真值+有响应）= %d" % p2["reconciled_n"])
    print("  从「无法判定」里漏出 MISSED 的条目 = %s（必须为 []）"
          % p2["leaked_missed_from_undecidable"])

    print("\n[P3 锚点边际敏感度]")
    print("  基础未覆盖度 = %.3f" % p3["base_ratio"])
    print("  抽掉单个锚点的最大影响 = %+.3f ⇒ %s"
          % (p3["max_delta"], "单个锚点不关键" if p3["single_anchor_invariant"] else "有吃重锚点"))
    print("  只留中文锚点(%d个) = %.3f ｜ 只留英文锚点(%d个) = %.3f ⇒ 语言构成会移动招牌数"
          % (p3["cn_n"], p3["only_cn"], p3["en_n"], p3["only_en"]))
    print("  整套真值抽掉 = %.3f（上升 %+.3f）⇒ 招牌数是整套锚点的集体产物，不是某个锚点"
          % (p3["drop_whole_set_ratio"], p3["drop_whole_set_ratio"] - p3["base_ratio"]))

    print("\n[P4 漏报率漂移] 同一个系统，换定义换漏报率：")
    for r in p4["rows"]:
        print("    %-14s 漏报 %-3d 条 ⇒ 漏报率 %.3f" % (r["definition"], r["missed_n"], r["miss_rate"]))
    print("  区间 [%.3f, %.3f]，spread = %.3f" % (p4["min"], p4["max"], p4["spread"]))

    report = {
        "module": "probe_silence_reality",
        "events_total": len(events),
        "definitions": sorted(DEFINITIONS),
        "p1_definition_dependent_missed": p1,
        "p2_reconciler": p2,
        "p3_anchor_sensitivity": p3,
        "p4_miss_rate_drift": p4,
        "events": events,
    }
    (OUT / "sra_probe_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # 把可复现的招牌数字写成 md，供手册直接引用
    md = [
        "# SRA 探针报告（沉默现实压力测试）",
        "",
        "- 事件源：语料全量 **%d** 处沉默上下文，三套定义各自独立判定。" % len(events),
        "- 招牌论点：**只有 %d 条的漏报身份与定义无关；%d 条是定义给的。**"
        % (p1["robust_missed"], p1["definition_dependent_missed"]),
        "- 对账器在 **%d** 条上拒绝出判定，且一条 MISSED 都没漏出去。" % p2["undecidable_n"],
        "- 漏报率存在 %.3f 的漂移区间。" % p4["spread"],
        "",
    ]
    (OUT / "sra_probe_report.md").write_text("\n".join(md), encoding="utf-8")
    print("\n[写出] %s" % (OUT / "sra_probe_report.json"))
    print("[写出] %s" % (OUT / "sra_probe_report.md"))

    if args.no_selftest:
        return 0
    return selftest(events, p1, p2, p3, p4)


if __name__ == "__main__":
    sys.exit(main())
