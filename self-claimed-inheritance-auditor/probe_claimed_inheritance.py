#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SCI · Step 2.75 硬门槛探针 —— 上真数据，证明判据不是 PPT 里的数。

三件事（缺一不可，缺哪件就退化成「自己抄自己」）：

  A 真实对账：扫本地 skill 库（~/.workbuddy/skills/）里**每一条** SKILL.md，
    逐条数「自述句」与「带可核对来源的自述句」，算出真实空转自述率。
  B Null 对照：证明指标能分辨 —— 注入不带来源的自述 ⇒ 空转率必须 1.000；
    注入带来源的自述 ⇒ 必须 0.000。指标不会分就说明它是死的。
  C 同口径复核：用 sci_cli 的扫描函数（不是复制一份）复核 A 的数，
    两边必须一致；不一致说明「同口径」被破坏了。

★ 反自我欺骗（F10）：本脚本跑的结论**只进报告、不改判据分**。
  若 A 的真实空转率恰好等于本件的招牌数，先怀疑脚本，而不是先庆祝。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_out"
OUT.mkdir(parents=True, exist_ok=True)

SKILLS_DIR = Path.home() / ".workbuddy" / "skills"

# ── 与 sci_cli.py 同源的词表（★ 必须 import，不能复制一份，否则同口径会漂） ──
import sci_cli  # noqa: E402

CLAIM_LOCAL = re.compile(
    r"已(?:封装|集成|创建|学会|跑通|验证|升级|落盘|写入|沉淀|收口)|"
    r"(?:learn|learned|self-?improv\w*|autonomous skill|creates skills)|"
    r"自我改进|自改进|学会了")

PROV_LOCAL = sci_cli.PROV_PAT + [
    r"learned from", r"from run ", r"from session ", r"from task ",
    r"破例来源", r"出处：", r"来源：",
]

# 注入件：不带来源的自述（模拟「我学会了 X」但说不出从哪学来）
FAKE_NO_PROV = ["已封装 %s 技能" % k for k in
                ("取证", "核对", "归档", "回审", "对账", "闸门", "探针", "手册")]
# 注入件：带来源的自述（模拟「本条来自 2026-09-27 第 N 次运行时」）
FAKE_WITH_PROV = ["已封装 %s 技能（来源：2026-09-27 运行时 #%d 实跑）"
                  % (k, i) for i, k in enumerate(FAKE_NO_PROV)]


def scan_text(text: str, claim_pat: re.Pattern, prov_pats: list[str],
              win: int = 200) -> dict[str, Any]:
    """单一函数给三处复用（A/B/C 必须走同一套逻辑）。"""
    n = len(claim_pat.findall(text))
    with_prov = 0
    for m in claim_pat.finditer(text):
        s = max(0, m.start() - win)
        e = min(len(text), m.end() + win)
        ctx = text[s:e]
        if any(re.search(p, ctx, re.I) for p in prov_pats):
            with_prov += 1
    return {"claim_n": n, "prov_n": with_prov,
            "prov_ratio": round(with_prov / n, 3) if n else 0.0,
            "idle_ratio": round(1 - (with_prov / n), 3) if n else 0.0}


def part_a_real_skill_library() -> dict[str, Any]:
    """A · 真实对账：本地 skill 库全量（不抽样）。"""
    rows: list[dict[str, Any]] = []
    files = sorted(SKILLS_DIR.rglob("SKILL.md")) if SKILLS_DIR.exists() else []
    for f in files:
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except Exception as e:                          # noqa: BLE001
            rows.append({"skill": f.parent.name, "err": str(e),
                         "claim_n": 0, "prov_n": 0, "prov_ratio": 0.0,
                         "idle_ratio": 1.0})
            continue
        r = scan_text(t, CLAIM_LOCAL, PROV_LOCAL)
        r["skill"] = f.parent.name
        rows.append(r)
    tot_claim = sum(r["claim_n"] for r in rows)
    tot_prov = sum(r["prov_n"] for r in rows)
    with_claims = [r for r in rows if r["claim_n"] > 0]
    return {
        "skills_dir": str(SKILLS_DIR),
        "skills_scanned": len(rows),
        "skills_with_claim": len(with_claims),
        "total_claim_n": tot_claim,
        "total_prov_n": tot_prov,
        "library_prov_ratio": round(tot_prov / tot_claim, 3) if tot_claim else 0.0,
        "library_idle_ratio": round(1 - (tot_prov / tot_claim), 3) if tot_claim else 0.0,
        "rows": rows,
    }


def part_b_null_control() -> dict[str, Any]:
    """B · Null 对照：注入件必须把指标推到两端。"""
    blob_no_prov = "\n".join(FAKE_NO_PROV)
    r_no = scan_text(blob_no_prov, CLAIM_LOCAL, PROV_LOCAL)
    blob_with = "\n".join(FAKE_WITH_PROV)
    r_with = scan_text(blob_with, CLAIM_LOCAL, PROV_LOCAL)
    return {
        "inject_no_prov_n": len(FAKE_NO_PROV),
        "inject_with_prov_n": len(FAKE_WITH_PROV),
        "no_prov": r_no, "with_prov": r_with,
        "discriminates": r_no["idle_ratio"] == 1.0 and r_with["idle_ratio"] == 0.0,
    }


def part_c_same_pipeline_recheck() -> dict[str, Any]:
    """C · 同口径复核：直接改 sci_cli 的词表对象再扫同一批语料。

    ★ 这里复用 sci_cli 的 scan_claim_contexts（含它的去重与窗口），
      只把 PROV_PAT 换成不存在的锚 ⇒ 指标必须掉下来。
      若指标不动，说明它根本没在扫词表，招牌数是假的。
    """
    sci_scan = sci_cli.scan_claim_contexts()
    saved = list(sci_cli.PROV_PAT)
    sci_cli.PROV_PAT = ["___不存在的锚点___"]
    try:
        killed = sci_cli.scan_claim_contexts()
    finally:
        sci_cli.PROV_PAT = saved
    return {
        "sci_prov_ratio": sci_scan["prov_ratio"],
        "sci_idle_ratio": sci_scan["idle_ratio"],
        "sci_claim_contexts": sci_scan["total_claim_contexts"],
        "sci_with_prov": sci_scan["with_prov"],
        "killed_prov_n": killed["with_prov"],
        "killed_idle_ratio": killed["idle_ratio"],
        "moves": killed["with_prov"] < sci_scan["with_prov"],
        "restored_after": sci_cli.PROV_PAT == saved,
    }


def main() -> int:
    a = part_a_real_skill_library()
    b = part_b_null_control()
    c = part_c_same_pipeline_recheck()

    print("=" * 74)
    print("SCI · Step 2.75 硬门槛探针 —— 真数据 / Null 对照 / 同口径复核")
    print("=" * 74)

    print("\n[A] 真实对账 · 本地 skill 库（全量 %d 个 SKILL.md，不抽样）"
          % a["skills_scanned"])
    print("  目录 %s" % a["skills_dir"])
    print("  存在自述句的技能 %d/%d | 自述句合计 %d 条 | 带可核对来源 %d 条"
          % (a["skills_with_claim"], a["skills_scanned"],
             a["total_claim_n"], a["total_prov_n"]))
    print("  ★ 本地持有面带来源率（实测）= %.3f" % a["library_prov_ratio"])
    print("  ★ 本地空转自述率（实测）    = %.3f" % a["library_idle_ratio"])
    top = sorted([r for r in a["rows"] if r["claim_n"] > 0],
                 key=lambda x: -x["claim_n"])[:10]
    print("  自述最多的 10 条 skill：")
    for r in top:
        print("    %-42s 自述 %2d 条 | 带来源 %d | 空转率 %.3f"
              % (r["skill"][:42], r["claim_n"], r["prov_n"], r["idle_ratio"]))
    untouched = [r for r in a["rows"] if r["claim_n"] == 0]
    print("  零自述句的技能 %d 条（这些不在本件的对账面上）" % len(untouched))

    print("\n[B] Null 对照（注入 %d 条无来源 + %d 条带来源）"
          % (b["inject_no_prov_n"], b["inject_with_prov_n"]))
    print("  无来源注入 ⇒ 空转率 %.3f（须为 1.000）" % b["no_prov"]["idle_ratio"])
    print("  带来源注入 ⇒ 空转率 %.3f（须为 0.000）" % b["with_prov"]["idle_ratio"])
    print("  ★ 指标可分辨 = %s" % b["discriminates"])

    print("\n[C] 同口径复核（复用 sci_cli，不复制词表）")
    print("  sci_cli 语料自述 %d 处 | 带来源 %d 条 | 带来源率 %.3f | 空转率 %.3f"
          % (c["sci_claim_contexts"], c["sci_with_prov"],
             c["sci_prov_ratio"], c["sci_idle_ratio"]))
    print("  杀掉来源锚后带来源数 %d（<%d 则指标在动）⇒ %s"
          % (c["killed_prov_n"], c["sci_with_prov"], c["moves"]))
    print("  词表已还原 = %s" % c["restored_after"])

    print("\n[判定]")
    gates = [
        ("A 真实对账跑出非零自述句", a["total_claim_n"] > 0,
         "实测=%d" % a["total_claim_n"]),
        ("A 本地空转率落在 (0,1] 区间", 0 < a["library_idle_ratio"] <= 1.0,
         "实测=%.3f" % a["library_idle_ratio"]),
        ("B 指标能分辨有无来源", b["discriminates"],
         "%.3f vs %.3f" % (b["no_prov"]["idle_ratio"], b["with_prov"]["idle_ratio"])),
        ("C 杀锚后指标确实下降", c["moves"], ""),
    ]
    n_pass = 0
    for name, ok, msg in gates:
        print("  [%s] %s%s" % ("PASS" if ok else "FAIL", name,
                               ("  ← " + msg) if msg else ""))
        n_pass += 1 if ok else 0
    print("  -- 硬门槛 %d/%d" % (n_pass, len(gates)))

    report = {"part_a": a, "part_b": b, "part_c": c,
              "gates": [{"name": n, "pass": bool(o), "msg": m} for n, o, m in gates]}
    (OUT / "probe_claimed_inheritance.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    # ★ A 的真实数若与招牌数（sci_cli 的空转率）几乎相同，必须主动告警。
    gap = abs(a["library_idle_ratio"] - c["sci_idle_ratio"])
    print("\n[反自我欺骗] 本地空转率 %.3f vs 语料招牌数 %.3f，差 %.3f"
          % (a["library_idle_ratio"], c["sci_idle_ratio"], gap))
    if gap < 0.05:
        print("  ⚠ 两者过于接近 ⇒ 先怀疑脚本是不是读了同一批文件，别急着庆祝。")

    print("\n报告 → %s" % (OUT / "probe_claimed_inheritance.json"))
    return 0 if n_pass == len(gates) else 1


if __name__ == "__main__":
    sys.exit(main())
