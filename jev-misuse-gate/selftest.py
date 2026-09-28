"""喂错数据自检 —— 它没报错，就是没写检查。

★ skill Step 5 第 6 项：任何自己写的校验器，上线前先喂一次错数据。
★ skill Step 5 第 7 项：**「改交付物」只是接受面的一半**，另一半是「改校验器读的那个源文件」。
  所以 5 条注入必须两侧都覆盖：
    #1 #2 改交付物（fixtures）
    #3 #4 改源文件（jvg_cli.py 的判据常量）
    #5 反向对照：不喂错数据时不得误报
  只测一侧 = 没测。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
CLI = os.path.join(HERE, "jvg_cli.py")
FIX = {name: os.path.join(HERE, "fixtures", name) for name in (
    "f01_math.py", "f02_clean.py")}
VERIFY = os.path.join(HERE, "verify.py")

fails: list[str] = []


def run_verify() -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, VERIFY], capture_output=True,
                          text=True, cwd=HERE)


def expect_red(tag: str, why: str, proc: subprocess.CompletedProcess) -> None:
    if proc.returncode == 0:
        fails.append(f"{tag} —— 喂错数据后校验器仍然全绿，说明这个检查没写：{why}")
        print(f"  ❌ {tag}\n        {why}\n        校验器输出：{proc.stdout.strip()[:200]}")
    else:
        red = [l for l in proc.stdout.splitlines() if "❌" in l]
        print(f"  ✅ {tag}\n        变红于：{red[0].strip() if red else '(非零退出)'}")


def with_cli_mutation(tag: str, old: str, new: str, why: str) -> None:
    """临时改 jvg_cli.py 的源码，跑校验器，然后**无条件还原**。"""
    backup = open(CLI, encoding="utf-8").read()
    if old not in backup:
        fails.append(f"{tag} —— 注入点没找到：{old[:40]}")
        print(f"  ❌ {tag}\n        注入点未找到：{old[:60]}")
        return
    try:
        open(CLI, "w", encoding="utf-8").write(backup.replace(old, new, 1))
        expect_red(tag, why, run_verify())
    finally:
        open(CLI, "w", encoding="utf-8").write(backup)
    restored = open(CLI, encoding="utf-8").read()
    if restored != backup:
        fails.append(f"{tag} —— 源文件未能还原，工程已损坏")
        print(f"  ❌ {tag} —— 源文件未还原！")


def inj1_deliverable_expected() -> None:
    """#1 交付物侧：把 f01 的算术那一行删掉 ⇒ 期望 math 却报不出来。"""
    tag, why = "注入#1 交付物侧（删 f01 的 sum 行）", "B01/E03 应该抓到 math 档从哪来的判定没了"
    backup = open(FIX["f01_math.py"], encoding="utf-8").read()
    try:
        open(FIX["f01_math.py"], "w", encoding="utf-8").write(
            backup.replace("    total = sum(l.amount for l in doc.lines)\n", ""))
        expect_red(tag, why, run_verify())
    finally:
        open(FIX["f01_math.py"], "w", encoding="utf-8").write(backup)


def inj2_deliverable_sneak() -> None:
    """#2 交付物侧：给 f02（声称干净）偷偷塞进同一上下文的 rm -rf ⇒ 必须被报出来。"""
    tag, why = "注入#2 交付物侧（往 f02 塞 rm -rf）", "E03 应该发现 f02 不再是干净的"
    backup = open(FIX["f02_clean.py"], encoding="utf-8").read()
    try:
        open(FIX["f02_clean.py"], "w", encoding="utf-8").write(
            backup.replace("def tag_of(row):",
                           "def tag_of(row):\n    subprocess.run(['rm', '-rf', row.tmp])"))
        expect_red(tag, why, run_verify())
    finally:
        open(FIX["f02_clean.py"], "w", encoding="utf-8").write(backup)


def inj3_source_wordlist() -> None:
    """#3 源文件侧：把不可逆词表改回匹配不到引号形态 —— 这正是 f04/f06 漏报的直接原因。"""
    with_cli_mutation(
        "注入#3 源文件侧（词表退回 \\brm\\s+-rf\\b）",
        old=r'r"\brm[^\w\n]*-rf\b|\b(?:delete|refund|transfer|payment|charge|migrat|"',
        new=r'r"\brm\s+-rf\b|\b(?:delete|refund|transfer|payment|charge|migrat|"',
        why="B03/B05 应该抓到引号形态又匹配不到了")


def inj4_source_window() -> None:
    """#4 源文件侧：把位置窗口放大到超过所有探针的距离 ⇒ 位置判据当场失效。"""
    with_cli_mutation(
        "注入#4 源文件侧（CONTEXT_LINES 放大到 999）",
        old="CONTEXT_LINES = 12", new="CONTEXT_LINES = 999",
        why="C01/C02 应该发现位置判据不再排除跨函数距离")


def inj5_reverse() -> None:
    """#5 反向对照：不喂错数据时，校验器必须**全绿**。误报同样说明它坏了。"""
    p = run_verify()
    if p.returncode != 0:
        fails.append("注入#5 反向对照 —— 正常状态就报错，校验器有误报")
        print(f"  ❌ 注入#5 反向对照（正常状态却报错）\n        {p.stdout[-400:]}")
    else:
        tail = [l for l in p.stdout.splitlines() if "通过" in l]
        print(f"  ✅ 注入#5 反向对照（正常状态全绿，{tail[-1].strip() if tail else '?' }）")


def main() -> int:
    print("JVG 喂错数据自检（交付物侧 2 条 + 源文件侧 2 条 + 反向对照 1 条）\n")
    inj1_deliverable_expected()
    inj2_deliverable_sneak()
    inj3_source_wordlist()
    inj4_source_window()
    inj5_reverse()
    print()
    if fails:
        print(f"✗ {len(fails)} 条注入没有如期变红 —— 校验器存在未覆盖的口子：")
        for f in fails:
            print(f"  · {f}")
        return 1
    print("✓ 5 条注入全部如期变红，且源文件已还原")
    return 0


if __name__ == "__main__":
    sys.exit(main())
