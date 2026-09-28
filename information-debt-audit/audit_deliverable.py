#!/usr/bin/env python3
"""
交付物对账器（第十件）

第十件的教训（第九件留下来的）：交付后回审不能只查「交付物里的数字有没有写错」，
还要查「量数字的那个工具本身是不是空的」。对账器第一版若只检查「正确数字有没有出现
在 HTML 里」，那么把数字改错它照样报通过 —— **能通过的检查等于没检查。**

所以它这里做三件事：
  ① 按 KPI 卡片逐格核对「显示的是不是这个值」（不是搜字符串）
  ② 自检项数不硬编码，现场跑一遍 verify.py 取真实数字
  ③ 已修掉的旧错值，出现即报警（防止回退）

用法：
    python audit_deliverable.py --html <手册.html>
退出码 0 = 对账通过，1 = 发现问题。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# ★ 2026-09-27 交付后回审抓到的真 bug（第十件）。
# 原写法 `rsplit("\\",1)[0] if "\\" in __file__ else rsplit("/",1)[0]` 在混合分隔符的
# __file__ 下会切错一层：verify.py 用 `HERE + "/audit_deliverable.py"` 拉起本脚本时，
# __file__ = "...\information-debt-audit/audit_deliverable.py"（正反斜杠混用），
# if 分支切在反斜杠上 ⇒ HERE 少一层 ⇒ 真数据文件指向了上层「突破件/」⇒ FileNotFoundError。
# 单跑时 __file__ 是裸文件名，走 else 分支得到空串，又"碰巧"能跑。
# **两种"能跑"靠的是不同机制，这才是祸根。** resolve().parent() 是唯一正确写法。
HERE = str(Path(__file__).resolve().parent)

# 本脚本若被 verify.py 拉起来，必须阻止它回头再跑 verify.py，否则无限递归。
# 第九件就是被这个伪装成「没能解析出自检总数」的 —— 报出来的根本不是同一回事。
SKIP_SELF = bool(os.environ.get("IDA_NO_RECURSE"))

MANUAL = Path.home() / "Desktop/成果/抖音学习突破七流程-信息债务审计器-2026-09-27.html"
REAL = Path(HERE, "audit_real.json")


def _load_real() -> dict:
    # 读不到就说人话（哪个文件、 Expect 什么），不要甩 Traceback。
    # 上一版就是直接 read_text ⇒ FileNotFoundError 从 line 40 冒出来，
    # 检查工具的"报错"长得像被检查对象的崩溃，根本分不清是谁的问题。
    if not REAL.exists():
        raise SystemExit(f"[对账器] 找不到真数据基线：{REAL}（HERE={HERE}）")
    return json.loads(REAL.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", default=str(MANUAL))
    args = ap.parse_args(argv)
    html = Path(args.html)
    text = html.read_text(encoding="utf-8") if html.exists() else ""

    problems: list[str] = []
    if not text:
        problems.append(f"手册不在路径 {html}，对账无法进行")

    data = _load_real()
    summ = data["summary"]
    n_trunc = summ["total_trunc"]
    n_tok = summ["total_debt_tokens"]
    n_sessions = summ["n_sessions"]

    # ---- ① 逐格核对真实数字（不是搜字符串）
    # 第九件第一版只检查「正确数字有没有出现」，把 1693 改成 2199 照样报通过。
    # 所以这里按「标签 -> 期望值」逐格核，而不是搜数字。
    kpis = {lbl: val for val, lbl in
            re.findall(r'<div class="n">(.*?)</div><div class="l">(.*?)</div>', text)}

    # 正文那句「合计：4 会话 / 2 次截断 / 累计丢 28316 token / 引用率 0.00 / 收尾债务比 0.9999」
    tail = re.search(r"合计[^。]{0,120}", text)
    if not tail:
        problems.append("没解析到「合计」句，真数据这一格已失去校验力")
    else:
        seg = tail.group(0)
        for want, pat in ((str(n_sessions), r"(\d+)\s*会话"),
                          (str(n_trunc), r"(\d+)\s*次截断"),
                          (str(n_tok), r"累计丢\s*(\d+)"),
                          ("0.00", r"引用率\s*([\d.]+)"),
                          ("0.9999", r"收尾债务比\s*([\d.]+)")):
            m = re.search(pat, seg)
            got = m.group(1) if m else None
            if got != want:
                problems.append(f"合计句里「{pat}」应为 {want}，实际 {got!r}")
        print(f"  合计句对账: {seg.strip()}")

    # ---- ② 自检项数：现场跑 verify.py，不硬编码
    n_checks = None
    if not SKIP_SELF:
        env = {**os.environ, "IDA_NO_RECURSE": "1"}
        v = subprocess.run([sys.executable, str(Path(HERE, "verify.py"))],
                           capture_output=True, text=True, timeout=300, env=env)
        m = re.search(r"IDA 自检: (\d+)/(\d+) 通过", v.stdout or "")
        if m:
            # 分子分母都要取。v1 只取了分子又拿它当分母，永远显示 X/X ——
            # 一个**只会对一半**的写法，和手册里只写一半数字是同一类错误。
            if m.group(1) != m.group(2):
                problems.append(f"verify 自检本身不自洽：{m.group(0)!r}")
            n_checks = f"{m.group(1)}/{m.group(2)}"
        else:
            problems.append("没能从 verify.py 解析出自检总数，该格已失去校验力")
    # 手册抬头那句是「自检 30/30 ｜ 真数据 4 会话实跑」
    # ★ 2026-09-27：`IDA_NO_RECURSE` 这把钥匙原本关了不止一扇门 ——
    # 它拦住递归，却把「自检项数」这一格也一起关掉了，而且**静默**。
    # 于是负向测试喂进错的项数，对账器照样报通过：一个从没跑过的检查。
    # 失效可以，必须留痕：这里是唯一能说明「这一格本次没查」的地方。
    if n_checks:
        m = re.search(r"自检\s*(\d+/\d+)", text)
        got = m.group(1) if m else None
        if got != n_checks:
            problems.append(f"抬头「自检」应为 {n_checks}，实际显示 {got!r}")
    else:
        print("  ⚠ 本次因递归防护未跑 verify，抬头「自检」这一格未被校验")

    # ---- ③ 五维均分必须自洽（不许只写结论）
    m5 = re.search(r"意义 ([\d.]+) / 结果 ([\d.]+) / 对齐 ([\d.]+) / "
                   r"(?:证据|\*{0,2}证据\*{0,2}) ([\d.]+) / 利益 ([\d.]+)",
                   text)
    if m5:
        parts = [float(x) for x in m5.groups()]
        avg = round(sum(parts) / len(parts), 2)
        if abs(avg - 3.48) > 0.005:
            problems.append(f"五维均分应为 3.48，按五个分数算出来是 {avg}")
    else:
        problems.append("没解析到五维评分，该格已失去校验力")

    # 补充：§二 线索表里那句「真数据 2 次截断 / 28316 token」也要对上。
    # 只对了合计句、漏了这里，就会出现「注入改动被合计句之外的格子吞掉」的错觉。
    lead = re.search(r"真数据\s*(\d+)\s*次截断\s*/\s*(\d+)\s*token", text)
    if not lead:
        problems.append("没解析到 §二 线索表的真数据一格，该格已失去校验力")
    else:
        for want, got in ((str(n_trunc), lead.group(1)), (str(n_tok), lead.group(2))):
            if got != want:
                problems.append(f"§二线索表应为 {want}，实际 {got!r}")

    # ---- ④ 已修掉的旧错值出现即报警
    # 注意：§七 会为了「记录这个错误」而引用旧值，所以只扫 KPI 区与正文表格，
    # 把说明性段落排除掉，别让检查误伤自己的病历。
    body = text.split('<h2 id="survey">')[0]
    for stale, why in (("291943", "superpowers 最新值是 291945"),
                       ("267931", "ECC 最新值是 267939")):
        if stale in body:
            problems.append(f"手册里仍残留旧值 {stale}（{why}）")

    # ---- ⑤ 手册标注的 skill 版本**不得比** SKILL.md 里真实的 version 更新
    # 2026-09-27 交付后回审：手册抬头写了 skill v2.6.0，而 SKILL.md 实际是 2.5.0 ——
    # 一个不存在的版本号。对账器此前完全不管这一格，等于这一格从没被检查过。
    # 「标注自己还没发生的版本」和「标注别的数字」是同一类错误，都要拦。
    skill_md = Path.home() / ".workbuddy/skills/zhengming-douyin-learn-breakthrough/SKILL.md"
    real_ver = None
    if skill_md.exists():
        mv = re.search(r"^version:\s*(\S+)\s*$", skill_md.read_text(encoding="utf-8"),
                       re.M)
        real_ver = mv.group(1) if mv else None
    else:
        problems.append(f"找不到 SKILL.md（{skill_md}），版本号这一格失去校验力")
    if real_ver:
        # 正则要照着**文件里实际的样子**写，不能照着"我以为它长这样"写。
        # 第一版漏了 `<code>` 前的空格，匹配不到，于是报 vNone —— 检查没跑成，
        # 还伪装成"这里有问题"。一律用 \s* 容错。
        mv_html = re.search(r"skill\s*<code>zhengming-douyin-learn-breakthrough"
                            r"</code>\s*v([\d.]+)", text)
        got = mv_html.group(1) if mv_html else None

        def _vt(s):
            return tuple(int(x) for x in re.findall(r"\d+", s or "")) or (0,)

        if got is None:
            problems.append("手册里没找到 skill 版本号标注，这一格失去校验力")
        elif _vt(got) > _vt(real_ver):
            # ★ 保留 2026-09-27 的初衷：抓「标注了还没发生的版本」
            #   （当时手册抬头写 v2.6.0，而 SKILL.md 实际只有 v2.5.0 —— 谎报未来）。
            problems.append(f"手册标注 skill v{got} 比 SKILL.md 实际的 v{real_ver} 还新"
                            " —— 标注了还没发生的版本")
        elif _vt(got) < _vt(real_ver):
            # ★ 2026-09-28 修：版本「落后于现状」不是缺陷。
            #   手册记录的是**本件生成时**的 skill 版本，skill 正常演进后必然落后。
            #   原先的 `got != real_ver` 把「演进」误判成「造假」，于是 skill 每升一次版，
            #   本件就永久自检失败（30/31），还连带触发对账器死锁 —— 一次升级，终身报警。
            #   留痕但**不拦**：只要不是"谎报未来"，就放行。
            print(f"  ⓘ 手册标注 skill v{got}（本件生成时的版本），SKILL.md 已演进"
                  f"到 v{real_ver} —— 版本演进不是缺陷，不拦")

    print("对账通过" if not problems else "对账发现问题：")
    for p in problems:
        print("  -", p)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
