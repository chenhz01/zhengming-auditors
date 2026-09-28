#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
交付物对账器 —— 把手册里写的每个数字，逐个跟 audit_real.json 对一遍。

为什么存在（2026-09-27 第九件教训）：
    LGA 自检 36/36 全绿，工具本身没有任何问题。
    但交付后回审发现：**手册 KPI 区写「实扫 2183 条条目」，实际是 1693** ——
    那个数字是凭印象手写的，没跟数据文件加总过。
    工具再绿，交付物里的手写数字照样能错。

用法：
    python audit_deliverable.py --html "<手册 HTML 绝对路径>"

退出码：0 = 全部对上；1 = 有不一致（会逐行打印）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--html", required=True, help="手册 HTML 路径")
    a = ap.parse_args()

    data = json.loads((HERE / "audit_real.json").read_text(encoding="utf-8"))
    html = Path(a.html).read_text(encoding="utf-8")

    problems: list[str] = []
    by_repo = {r["repo"]: r for r in data if r.get("mode") == "audit"}

    # ---- 1. 表格逐格对账
    for repo, r in by_repo.items():
        m = re.search(re.escape(repo) + r"</td>.*?</tr>", html, re.S)
        if not m:
            problems.append(f"{repo}: HTML 里找不到对应表格行")
            continue
        seg = m.group(0)
        checks = {
            "可执行率": round(r["actionability"] * 100, 1),
            "闭环率": round(r["closure_rate"] * 100, 1),
            "保鲜风险": round(r["freshness_ratio"] * 100),
        }
        for label, val in checks.items():
            if f"{val}%" not in seg:
                problems.append(f"{repo} {label}: 应为 {val}%，手册里没有")
        if f'>{r["n_items"]}<' not in seg:
            problems.append(f'{repo} 条目数: 应为 {r["n_items"]}')
        want_md = f'{r["files_scanned"]}/{r["files_total"]}'
        if want_md not in seg:
            problems.append(f"{repo} md: 应为 {want_md}")

    # ---- 2. KPI 卡片逐个对账（2183 就是在这里写错的）
    #
    # 这里的坑（2026-09-27 当场撞上）：第一版只检查「正确数字有没有出现在 HTML 里」，
    # 结果把 KPI 改成 2199 它照样报通过 —— 因为它根本没验证"显示的是不是这个数"。
    # 跟第八件的 `rc in (0, 2)` 空断言同族：**能通过的检查等于没检查。**
    # 所以必须按「标签 -> 期望值」逐张卡核，而不是搜字符串。
    total_items = sum(r.get("n_items", 0) for r in data)
    total_files = sum(r.get("files_scanned", 0) for r in data)
    total_meta = sum(r.get("n_meta", 0) for r in data)

    # findall 返回的是 (数值, 标签)，要翻成 {标签: 数值} 才能按标签查。
    # 第一版直接 dict() 了，键值和标签正好反着，于是怎么查都是 None，
    # 而"没识别到 KPI"的兜底又被输出顺序盖住了 —— 又一个靠打印顺序藏问题的坑。
    kpis = {lbl: val for val, lbl in
            re.findall(r'<div class="n">(.*?)</div><div class="l">(.*?)</div>', html)}
    # 自检项数不硬编码：当场跑一遍 verify.py 取真实数字。
    # 硬编码的代价 2026-09-27 已经付过一次——自检从 36 加到 38 后，
    # 对账器里那个 36/36 失真了，反而报出一堆假不一致。
    # 守卫：本脚本若是被 verify.py 拉起来的，就别再回头去跑 verify.py —— 否则
    # verify -> 对账器 -> verify -> 对账器 无限递归，60 秒超时，
    # 报出来的却是"没解析出自检总数"，把递归问题伪装成一个假的数字不一致。
    skip_self = bool(os.environ.get("LGA_NO_RECURSE"))
    if skip_self:
        # 被 verify.py 拉起时跳过：外层那一次已经真跑过 verify.py 了，
        # 这里再跑一次就是 verify -> 对账器 -> verify 的无限递归。
        n_checks = None
    else:
        env = {**os.environ, "LGA_NO_RECURSE": "1"}
        v = subprocess.run([sys.executable, str(HERE / "verify.py")],
                           capture_output=True, text=True, timeout=300, env=env)
        m = re.search(r"LGA 自检: (\d+)/\d+ 通过", v.stdout or "")
        if m:
            n_checks = m.group(1) + "/" + m.group(1)
        else:
            n_checks = "?"
            problems.append("没能从 verify.py 解析出自检总数，自检项数这一格已失去校验力")

    expect = {
        "自检通过": n_checks,
        "真数据仓库": str(len(by_repo)),
        "实扫条目（%d 个 md）" % total_files: str(total_items),
        "意义 / 结果维": "3.8",
        "二手清单路径错误": "3/3",
    }
    for label, want in expect.items():
        if want is None:
            continue  # 这一格本轮无法自证，留待外层
        got = kpis.get(label)
        if got != want:
            problems.append(f"KPI「{label}」应为 {want}，实际显示 {got!r}")
    # 兜底：一张卡都没识别到，说明检查器自己失效了，上面的"全是 None"就不可信
    if not kpis:
        problems.append("没在 HTML 里识别到任何 KPI 卡片 —— 检查器可能失效，以上不可信")

    # ---- 3. 已修掉的旧错值，出现即报警
    # 注意：§7 会为了"记录这个错误"而引用 2183，那是刻意的，
    # 得把它所在段落排除掉，否则检查会误伤自己的病历。
    audit_prose = re.split(r'<h2 id="audit">.*?(?=<h2 id="score">)', html, flags=re.S)
    body = audit_prose[0] if audit_prose else html
    for stale in ("2183",):
        if stale in body:
            problems.append(f"手册正文里仍残留错误数字 {stale}（正确值 {total_items}）")

    print("=" * 60)
    print(f"仓库数   {len(by_repo)}")
    print(f"md 文件  {total_files}")
    print(f"条目总数 {total_items}（其中已勾选事记 {total_meta}，不计入分母）")
    print("=" * 60)
    if problems:
        print("对账未通过：")
        for p in problems:
            print(f"  [不一致] {p}")
        return 1
    print("对账通过：手册表格与真数据逐格一致")
    return 0


if __name__ == "__main__":
    sys.exit(main())
