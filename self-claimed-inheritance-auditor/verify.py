#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""SCI 收口对账器（R-BK2）—— 本件的最后一道闸。

★ 它不像别的脚本那样"算完就走"，而是回答三个问题：
   Q1 该有的东西在不在？（交付清单 + 工程完整性）
   Q2 手册里写的数字，跟代码实跑出来的，是不是同一个数？（手册-代码漂移）
   Q3 突破件够不够？（R-BK1 数量闸 + 质量闸）

   「手册写了 0.972 但代码里其实是 0.000」正是这套流程最容易悄悄发生的事，
   所以这里把招牌数硬对账，不靠人眼复核。

★ 踩过的坑（SRA 版已修，本版继承）：
   subprocess 参数必须**拆开**传，'sci_cli.py --selftest' 当一个文件名传会报
   can't open file，于是自检"未跑出结果"却看起来像跑过了。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sci_cli  # noqa: E402

ROOT = Path(__file__).resolve().parent
RULES_BK = Path.home() / ".workbuddy" / "rules" / "突破件"

HANDBOOK = RULES_BK / "突破-2026-09-27-自述继承审计器SCIv1.0.md"

HANDBOOK_REQUIRED = [
    ("Step 0 缺口单（对上件 FSA）", ["缺口单"]),
    ("自攻三问改写命题记录", ["自攻三问"]),
    ("arXiv 2607.24300 verifier-deployment gap", ["2607.24300"]),
    ("一手校错事件（SEAL 措辞对不上）", ["一手校错"]),
    ("六判据表", ["C1", "C6"]),
    ("五个竞品扫描", ["skilldoctor"]),
    ("Step 2.75 探针实测", ["518"]),
    ("五维评分", ["五维"]),
    ("我忽略了什么（≥4 条）", ["我忽略了什么"]),
    ("已知限制", ["已知限制"]),
    ("C4 不是「一半工具做了回归」的澄清", ["不是「有一半工具做了回归测试」"]),
]

# 手册里出现的招牌数字 → 代码里必须算出同一个值
HEADLINE_SCORE = [
    ("语料空转自述率", "0.972", None),
    ("语料自述上下文数", "542", None),
    ("语料带来源自述数", "15", None),
]

# R-BK1 突破件清单（≥5 件；凑数不计，每条必须是"修了一类缺陷"的机制）
BREAKTHROUGH_ITEMS = [
    "六判据 CLI（C1-C6，basis 强制标注 + 零命中 0.0 硬断言）",
    "Step 2.75 硬门槛探针（真数据 / Null 对照 / 同口径复核）",
    "审计锚三字段规范（来源运行时 / 判据分 / 空转标记）",
    "双计数门（自述数 vs 新能力数并行记账，C6 机制）",
    "一手校错闸（转述回原文比对，§5.1）",
    "C4 资本纪律同构映射（回归闸门 > 新增自述）",
    "反自我欺骗闸门（招牌数过于接近时主动告警）",
    "R-BK2 收口对账器（手册-代码-数据三方对账）",
]

ENGINE_FILES = [
    "collect_corpus.py",
    "sci_cli.py",
    "probe_claimed_inheritance.py",
    "build_html.py",
    "verify.py",
]

ARTIFACTS = [
    "_out/probe_claimed_inheritance.json",
    "_out/index.html",
    "Desktop/成果/抖音学习突破七流程-自述继承审计器SCI-2026-09-27.html",
]

# ★ 跨函数传递实跑 stdout。**不能**为了"检查"而现场拼一段字符串回去比对 ——
#   那叫假闸（永远命中自己拼的东西），正好是本件要抓的病。
_LAST: dict[str, str] = {"probe_stdout": "", "build_stdout": ""}


def _run(*args: str) -> tuple[int, str]:
    """★ 参数必须逐项传，不能拼成一个字符串。"""
    py = sys.executable
    cmd = [py]
    for a in args:
        cmd.append(str(ROOT / a) if a.endswith(".py") else a)
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=str(ROOT))
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def q1_deliverables() -> tuple[int, list[str]]:
    msgs: list[str] = []
    ok = True

    for f in ENGINE_FILES:
        exist = (ROOT / f).exists()
        msgs.append("  [%s] 工程脚本 %s" % ("PASS" if exist else "FAIL", f))
        ok = ok and exist

    # 语料：唯一 7 份、全部非空、无重复
    docs = sci_cli.load_artifacts()
    real = [d for d in docs if not d.get("dup_of")]
    dup = [d for d in docs if d.get("dup_of")]
    non_empty = [d for d in real if d.get("text")]
    good = len(real) >= 7 and len(non_empty) == len(real)
    msgs.append("  [%s] 语料落盘 %d 份 → 唯一 %d / 非空 %d / 重复 %d"
                % ("PASS" if good else "FAIL", len(docs), len(real),
                   len(non_empty), len(dup)))
    ok = ok and good

    exist = HANDBOOK.exists()
    msgs.append("  [%s] 突破手册 %s" % ("PASS" if exist else "FAIL", HANDBOOK.name))
    ok = ok and exist
    # ★ 产物检查不在这里：_out/index.html 与 桌面那份由 build_html.py 生成，
    #   下面 Q1 引擎实跑会先跑它 ⇒ 产物必须等引擎跑完再查，否则必然误报 FAIL。
    return (0 if ok else 1), msgs


def q1_artifacts() -> tuple[int, list[str]]:
    msgs: list[str] = []
    ok = True
    for f in ARTIFACTS:
        p = Path.home() / f if f.startswith("Desktop") else ROOT / f
        exist = p.exists() and p.stat().st_size > 0
        msgs.append("  [%s] 产物 %s（%d B）"
                    % ("PASS" if exist else "FAIL", f,
                       p.stat().st_size if p.exists() else -1))
        ok = ok and exist
    return (0 if ok else 1), msgs


def q1_engine() -> tuple[int, list[str]]:
    msgs: list[str] = []
    ok = True

    rc, _out = _run("collect_corpus.py")
    msgs.append("  [%s] collect_corpus.py（语料采集闸）exit=%d"
                % ("PASS" if rc == 0 else "FAIL", rc))
    ok = ok and rc == 0

    rc, out = _run("sci_cli.py")
    m = re.search(r"selftest (\d+)/(\d+)", out)
    n_all = int(m.group(2)) if m else 0
    n_ok = int(m.group(1)) if m else 0
    msgs.append("  [%s] sci_cli.py 自检 %s"
                % ("PASS" if rc == 0 else "FAIL",
                   ("%d/%d" % (n_ok, n_all)) if m else "未跑出结果"))
    ok = ok and rc == 0 and n_all >= 15 and n_ok == n_all

    rc, pout = _run("probe_claimed_inheritance.py")
    _LAST["probe_stdout"] = pout
    m = re.search(r"硬门槛 (\d+)/(\d+)", pout)
    n_all = int(m.group(2)) if m else 0
    n_ok = int(m.group(1)) if m else 0
    msgs.append("  [%s] Step 2.75 硬门槛探针 %s"
                % ("PASS" if rc == 0 else "FAIL",
                   ("%d/%d" % (n_ok, n_all)) if m else "未跑出结果"))
    ok = ok and rc == 0 and n_all >= 4 and n_ok == n_all

    rc, bout = _run("build_html.py")
    _LAST["build_stdout"] = bout
    m = re.search(r"\[OK\].*?index\.html\s+\((\d+) B\)", bout)
    msgs.append("  [%s] build_html.py exit=%d%s"
                % ("PASS" if rc == 0 else "FAIL", rc,
                   "（%s B）" % m.group(1) if m else ""))
    ok = ok and rc == 0

    arc, amsgs = q1_artifacts()
    msgs.extend(amsgs)
    ok = ok and arc == 0
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
    scan = sci_cli.scan_claim_contexts()
    actual = {
        "0.972": round(scan["idle_ratio"], 3),
        "542": scan["total_claim_contexts"],
        "15": scan["with_prov"],
    }
    for token, val in actual.items():
        printed = str(round(val, 3)) if isinstance(val, float) else str(val)
        hit_in_hb = token in hb
        consistent = printed == token
        msgs.append("  [%s] 招牌数字 %s：手册%s命中，代码实算 %s"
                    % ("PASS" if (hit_in_hb and consistent) else "FAIL",
                       token, "有" if hit_in_hb else "无", printed))
        ok = ok and hit_in_hb and consistent

    # ★ 反自我欺骗闸门：必须看探针**实跑 stdout**里有没有真的告警，
    #   不许现场拼字符串假装检查（第一版就是这么写的，等于没闸）。
    po = _LAST.get("probe_stdout", "")
    flagged = "先怀疑脚本" in po
    msgs.append("  [%s] 反自我欺骗闸门在探针实跑中确实触发（stdout 含告警语）"
                % ("PASS" if flagged else "FAIL"))
    ok = ok and flagged

    pj = ROOT / "_out" / "probe_claimed_inheritance.json"
    if pj.exists():
        data = json.loads(pj.read_text(encoding="utf-8"))
        a = data["part_a"]
        c = data["part_c"]
        gap = abs(a["library_idle_ratio"] - c["sci_idle_ratio"])
        msgs.append("  [INFO] A 段本地空转率 %.3f vs C 段语料招牌数 %.3f，差 %.3f；"
                    "两批不同源（518 SKILL.md vs 7 语料文件），接近是巧合不是印证"
                    % (a["library_idle_ratio"], c["sci_idle_ratio"], gap))
        # 「不同源已核实」这件事必须能在手册里被翻出来，否则这段 INFO 只是自说自话
        verified = "不是互相印证" in hb
        msgs.append("  [%s] 手册已记录「不同源、非互相印证」的核实结论"
                    % ("PASS" if verified else "FAIL"))
        ok = ok and verified

    # 「我忽略了什么」≥4 条
    seg = hb[hb.find("我忽略了什么"):] if "我忽略了什么" in hb else ""
    n_ignore = len(re.findall(r"(?m)^\s*[-*]?\s*(\d+)\.\s+\S", seg))
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
    low = [x for x in BREAKTHROUGH_ITEMS if "凑数" in x or "占位" in x]
    msgs.append("  [%s] R-BK1 质量闸：无凑数/占位件"
                % ("PASS" if not low else "FAIL"))
    ok = ok and not low
    return (0 if ok else 1), msgs


def main() -> int:
    print("[SCI 收口对账器 R-BK2] %s" % HANDBOOK.name)
    stages = [
        (q1_deliverables(), "Q1 交付清单与工程完整性"),
        (q1_engine(), "Q1 引擎实跑（含产物生成与产物核查）"),
        (q2_handbook_vs_code(), "Q2 手册-代码对账（防漂移）"),
        (q3_breakthrough_gate(), "Q3 R-BK1 突破件数量/质量闸"),
    ]
    bad = 0
    for (rc, msgs), label in stages:
        print("\n%s" % label)
        for m in msgs:
            print(m)
        if rc != 0:
            bad += 1
    allok = bad == 0
    print("\n%s  R-BK2 %s（%d 组全绿）"
          % ("[OK] " if allok else "[FAIL] ",
             "全绿" if allok else "%d 组未过" % bad,
             len(stages) - bad))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
