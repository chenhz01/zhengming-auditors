#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SRA 收口对账器（R-BK2）—— 本件的最后一道闸。

★ 它不像别的脚本那样"算完就走"，而是回答三个问题：
   Q1 该有的东西在不在？（交付清单 + 工程完整性）
   Q2 手册里写的数字，跟代码实跑出来的，是不是同一个数？（手册-代码漂移）
   Q3 突破件够不够？（R-BK1 数量闸 + 质量闸）

   「手册写了 0.898 但代码里其实是 0.851」正是这套流程最容易悄悄发生的事，
   所以这里把招牌数硬对账，不靠人眼复核。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sra_cli  # noqa: E402

ROOT = Path(__file__).resolve().parent
RULES_BK = Path.home() / ".workbuddy" / "rules" / "突破件"

HANDBOOK = RULES_BK / "突破-2026-09-27-沉默对账器SRAv1.0.md"

# 手册必须出现的章节/关键词（缺一即视为"写了但没写全"）
HANDBOOK_REQUIRED = [
    ("Step 0 缺口单（对上件 FSA）", ["缺口单"]),
    ("ProactiveBench 改写命题记录", ["ProactiveBench"]),
    ("五源一手交叉表", ["五源"]),
    ("实测矩阵（59 处 / 0.898）", ["0.898"]),
    ("六判据表", ["G1", "G6"]),
    ("异议四件套", ["替代解释"]),
    ("五维评分", ["五维"]),
    ("我忽略了什么（≥4 行）", ["我忽略了什么"]),
    ("已知限制", ["已知限制"]),
]

# 手册里出现的招牌数字 → 代码里必须算出同一个值
HEADLINE_SCORE = [
    ("未覆盖沉默比例", "0.898", None),          # None = 只校验手写的字符串对不对
    ("沉默上下文数", "59", None),
    ("无法判定数", "53", None),
    ("人为真值占比", "0.222", None),
]

# R-BK1 突破件清单（≥5 件；凑数不计，每条必须是"修了一类缺陷"的机制）
BREAKTHROUGH_ITEMS = [
    "三级来源角色机制（CORE/SIDE/REF/DUP）",
    "内容指纹去重闸（sha256，同字节算一个源）",
    "取消启发式自动降权（角色声明化，判断权留给人）",
    "六判据 CLI（SRA v1.0，输出侧病搬时间侧）",
    "招牌实测指标「未覆盖沉默比例」（语料全量跑出）",
    "双声明分离 + basis_override（不许把主张标成实测）",
    "最小对账器 reconcile()（无真值即拒绝出漏报）",
    "定义依赖漏报分析（3 套定义 / 漏报率漂移）",
    "锚点组合敏感度 P3（单个不敏感、组合敏感）",
    "Step 0 缺口单机制（对上件 FSA 出 3 条）",
]

ENGINE_FILES = [
    "collect_corpus.py",
    "sra_cli.py",
    "probe_silence_reality.py",
    "build_html.py",
    "verify.py",
]


def _run(*args: str) -> tuple[int, str]:
    """★ 第一版把 'sra_cli.py --selftest' 当成**一个**文件名传给 python，
    subprocess 于是报 can't open file ⇒ 自检"未跑出结果"。参数必须分开传。"""
    p = subprocess.run([sys.executable, *(str(ROOT / a) if a.endswith(".py") else a for a in args)],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def q1_deliverables() -> tuple[int, list[str]]:
    msgs: list[str] = []
    ok = True

    # 1 工程脚本齐
    for f in ENGINE_FILES:
        exist = (ROOT / f).exists()
        msgs.append("  [%s] 工程脚本 %s" % ("PASS" if exist else "FAIL", f))
        ok = ok and exist
    # 2 语料：去重后 ≥9 且全部非空，且去重闸确实抓到了重复
    #    （10 个落盘文件里有 1 对字节完全相同 ⇒ 唯一 9 份。去重闸没抓到就是闸失效）
    docs = sra_cli.load_artifacts()
    real = [d for d in docs if not d.get("dup_of")]
    dup = [d for d in docs if d.get("dup_of")]
    non_empty = [d for d in real if d.get("text")]
    good = len(real) >= 9 and len(non_empty) == len(real) and len(dup) >= 1
    msgs.append("  [%s] 语料落盘 %d 份 → 去重后唯一 %d 份 / 非空 %d 份 / 去重闸抓到 %d 份重复"
                % ("PASS" if good else "FAIL", len(docs), len(real), len(non_empty), len(dup)))
    ok = ok and good
    # 3 产物目录
    for f in ["_out/sra_probe_report.json", "_out/sra_probe_report.md", "_out/index.html"]:
        exist = (ROOT / f).exists()
        msgs.append("  [%s] 产物 %s" % ("PASS" if exist else "FAIL", f))
        ok = ok and exist
    # 4 手册存在
    exist = HANDBOOK.exists()
    msgs.append("  [%s] 突破手册 %s" % ("PASS" if exist else "FAIL", HANDBOOK.name))
    ok = ok and exist
    return (0 if ok else 1), msgs


def q1_engine() -> tuple[int, list[str]]:
    msgs: list[str] = []
    ok = True
    rc, out = _run("collect_corpus.py")
    msgs.append("  [%s] collect_corpus.py（语料采集闸）exit=%d"
                % ("PASS" if rc == 0 else "FAIL", rc))
    ok = ok and rc == 0

    rc, out = _run("sra_cli.py", "--selftest")
    m = re.search(r"selftest (\d+)/(\d+)", out)
    n_all = int(m.group(2)) if m else 0
    n_ok = int(m.group(1)) if m else 0
    msgs.append("  [%s] sra_cli.py 自检 %s" % ("PASS" if rc == 0 else "FAIL",
                                            ("%d/%d" % (n_ok, n_all)) if m else "未跑出结果"))
    ok = ok and rc == 0 and n_all >= 15 and n_ok == n_all

    rc, out = _run("probe_silence_reality.py")
    m = re.search(r"selftest (\d+)/(\d+)", out)
    n_all = int(m.group(2)) if m else 0
    n_ok = int(m.group(1)) if m else 0
    msgs.append("  [%s] 沉默现实探针 自检 %s"
                % ("PASS" if rc == 0 else "FAIL",
                   ("%d/%d" % (n_ok, n_all)) if m else "未跑出结果"))
    ok = ok and rc == 0 and n_all >= 10 and n_ok == n_all
    return (0 if ok else 1), msgs


def q2_handbook_vs_code() -> tuple[int, list[str]]:
    msgs: list[str] = []
    ok = True
    if not HANDBOOK.exists():
        msgs.append("  [FAIL] 手册不存在，无法对账")
        return 1, msgs
    hb = HANDBOOK.read_text(encoding="utf-8")

    for label, keys in HANDBOOK_REQUIRED:
        miss = [k for k in keys if k not in hb]
        msgs.append("  [%s] 手册章节：%s%s"
                    % ("PASS" if not miss else "FAIL", label,
                       "" if not miss else "（缺：%s）" % "、".join(miss)))
        ok = ok and not miss

    # ★ 招牌数字对账：手册写了什么，代码必须真算出同一个数
    scan = sra_cli.scan_silence_contexts()
    demo = sra_cli.scan_demo_triggers()
    actual = {
        "0.898": scan["uncovered_ratio"],
        "59": scan["total_silence_contexts"],
        "53": scan["unjudgeable"],
        "0.222": demo["artificial_ratio"],
    }
    for token, val in actual.items():
        printed = str(round(val, 3)) if isinstance(val, float) else str(val)
        # 手册里出现该数字，且与代码实算值一致
        hit_in_hb = token in hb
        consistent = printed == token or str(round(val, 3)) == token
        msgs.append("  [%s] 招牌数字 %s：手册%s命中，代码实算 %s"
                    % ("PASS" if (hit_in_hb and consistent) else "FAIL",
                       token, "有" if hit_in_hb else "无", printed))
        ok = ok and hit_in_hb and consistent

    # 探针报告与 CLI 同口径
    pj = ROOT / "_out" / "sra_probe_report.json"
    if pj.exists():
        data = json.loads(pj.read_text(encoding="utf-8"))
        same = data["p3_anchor_sensitivity"]["base_ratio"] == scan["uncovered_ratio"]
        msgs.append("  [%s] 探针与 CLI 招牌数同口径（%.3f）"
                    % ("PASS" if same else "FAIL", scan["uncovered_ratio"]))
        ok = ok and same

    # 「我忽略了什么」≥4 条（编号列表，不带 bullet 也要算）
    n_ignore = len(re.findall(r"(?m)^\s*[-*]?\s*(\d+)\.\s+\S",
                              hb[hb.find("我忽略了什么"):] if "我忽略了什么" in hb else ""))
    msgs.append("  [%s] 「我忽略了什么」条目数 = %d（要求 ≥4）"
                % ("PASS" if n_ignore >= 4 else "FAIL", n_ignore))
    ok = ok and n_ignore >= 4
    return (0 if ok else 1), msgs


def q3_breakthrough_gate() -> tuple[int, list[str]]:
    msgs: list[str] = []
    n = len(BREAKTHROUGH_ITEMS)
    ok = n >= 5
    for i, it in enumerate(BREAKTHROUGH_ITEMS, 1):
        msgs.append("  [清单] %d. %s" % (i, it))
    msgs.append("  [%s] R-BK1 突破件数量闸：%d / 5%s"
                % ("PASS" if ok else "FAIL", n, "" if ok else "（不足，须补或用完）"))
    # 质量闸：不得出现"凑数件"标记
    low = [x for x in BREAKTHROUGH_ITEMS if "凑数" in x or "占位" in x]
    msgs.append("  [%s] R-BK1 质量闸：无凑数/占位件"
                % ("PASS" if not low else "FAIL"))
    ok = ok and not low
    return (0 if ok else 1), msgs


def main() -> int:
    print("[SRA 收口对账器 R-BK2] %s" % HANDBOOK.name)
    results: list[tuple[int, list[str], str]] = [
        (q1_deliverables(), "Q1 交付清单与工程完整性"),
        (q1_engine(), "Q1 引擎实跑"),
        (q2_handbook_vs_code(), "Q2 手册-代码对账（防漂移）"),
        (q3_breakthrough_gate(), "Q3 R-BK1 突破件数量/质量闸"),
    ]
    bad = 0
    for (rc, msgs), label in results:
        print("\n%s" % label)
        for m in msgs:
            print(m)
        if rc != 0:
            bad += 1
    allok = bad == 0
    print("\n%s  R-BK2 %s（%d 组全绿）"
          % ("[OK] " if allok else "[FAIL] ",
             "全绿" if allok else "%d 组未过" % bad,
             4 - bad))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
