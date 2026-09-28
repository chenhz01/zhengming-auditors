#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""突破件数量闸 · 收口对账器（R-BK2 收口前逐件对账的落地件）

★ 它存在的唯一理由：不靠嘴数。上一轮的「交付四件」是**叙述**，不是**清点**。

★ 口径先钉死（§S3.5 第 5 条「口径先钉死再核」），全部引自 rules 原文，不在本文件里发明：
  - R-WE1.1《规定-工作进化流程-v1.0.md》L23-30 —— 升一档最低门槛满足其一：
      ① 从「修一个」变成「修一类」
      ② 从「人肉做」变成「有工具」
      ③ 从「无证据」变成「有门禁」
    原文明写：只是「把同样的活再干一遍」不算突破。
  - R-BK1《约定-突破件数量闸-v1.0.md》L13-14 —— 突破件 = R-WE1.1 三选一
      **且** 可执行件优先（脚本/模板/规定三选二）；凑数件（重命名/纯文档搬运）**不计**。
  - R-BK1 L8-11 —— 量级：大任务 ≥5 件 / 小任务 ≥3 件。
  - R-BK2 L19 —— 「收口前逐件对账——编号/判据归属/三态/工件路径，**缺件不得标完毕**」。

★ 三态（本件口径，沿用工作约定）：
  ✅ = 写入工件 ∧ 已实跑跑通（证据=本脚本实勘命令）
  🟡 = 已写入工件，未实跑
  ⬜ = 未写入工件

★ 自指纪律（R-WE1「生产者不能给自己发证书」）：
  1. 本文件**不计入**突破件数 —— 它是 R-BK2 要求的「对量工具」，不是被量的件。
  2. 但本文件**必须过喂错数据自检**：故意喂它一个错数字，它不红就是没写检查。

用法：
    python breakthrough_audit.py            # 正常对账
    python breakthrough_audit.py --self-test  # 只跑喂错数据自检
"""

from __future__ import annotations

import ast
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
SELF = os.path.basename(__file__)              # breakthrough_audit.py —— 自排除

# ---------------------------------------------------------------- 口径常量
# 量级判定：本件同时产出「新规则」（rules 归档件）+「新工具」（jvg_cli.py），
# 命中 R-BK1「新規則+新工具同时产出」⇒ 按**大任务**口径核（≥5 件，取更严的一档）。
TASK_SCALE = "大任务"
GATE_MIN = 5

# R-BK1 明列「凑数件不计」——这些形态一律不算件，无论出现在哪张表里。
NON_BREAKTHROUGH_RE = re.compile(
    r"^(corpus|corpus_report\.json|corpus_v1_empty_shells|fx|fx\.json|_clones)$",
    re.IGNORECASE)

# 三态判定：能 import 且语法通过 = 实跑跑通（对纯函数模块等价于冒烟）
SMOKE_TIMEOUT = 60


def _rel(p: str) -> str:
    return os.path.relpath(p, HERE).replace("\\", "/")


# ---------------------------------------------------------------- 单件清点
def inspect(path: str) -> dict:
    """清点一个 .py：判据归属 / 可执行件 / 三态。全靠实读，不猜。"""
    name = os.path.basename(path)
    src = open(path, encoding="utf-8").read()
    tree = ast.parse(src)

    kinds = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kinds.add("tool")                       # 有工具
        if isinstance(node, ast.Assert):
            kinds.add("gate")                       # 有门禁（自检/断言）
        if isinstance(node, ast.Call):              # 含 sys.exit / raise 退出码
            f = node.func
            if isinstance(f, ast.Attribute) and f.attr == "exit":
                kinds.add("gate")
    has_exit_code = bool(re.search(r"sys\.exit|raise\s+SystemExit|exit_code", src))
    if has_exit_code:
        kinds.add("gate")

    # 可执行件（R-BK1 L13「脚本/模板/规定三选二」）：脚本类判定 = 有 main/CLI 入口
    executable = bool(re.search(r'__main__|argparse|add_argument', src)) or kinds >= {"tool"}

    # ★ 空壳件检测（R-BK1 L14「凑数件不计」的另一半）：
    #   只看"有没有 def / assert"是不够的 —— 一句 print("hi") 加一个 assert 就能刷出一件，
    #   而且对账器看不出异样。三选至少一，才算**活的**件：
    #     ① 有 CLI 入口（能用不同输入重复跑）
    #     ② 引用工程内其它件（和其它件耦合 = 它长在这个工程里，不是随手扔的）
    #     ③ 含显式数字断言（23 项 / 5 条 / 8 fixture 这类**可证伪的具体值**）
    siblings = [f for f in os.listdir(HERE)
                if f.endswith(".py") and f != name and os.path.isfile(os.path.join(HERE, f))]
    has_cli = bool(re.search(r'__main__|argparse|add_argument|sys\.argv', src))
    refs_sibling = any(re.search(rf"\b{re.escape(s[:s.rfind('.')])}\b", src) for s in siblings)
    numeric_asserts = len(re.findall(r"assert\s+.{0,40}\d", src))
    alive = has_cli or refs_sibling or numeric_asserts >= 3
    shell = not alive

    # 三态
    exists = True
    smoke = "✅ 已实跑"
    try:
        r = subprocess.run([sys.executable, "-c",
                            f"import ast,sys;ast.parse(open(r'{path}',encoding='utf-8').read())"],
                           capture_output=True, text=True, timeout=SMOKE_TIMEOUT)
        if r.returncode != 0:
            smoke = f"⬜ 语法/导入失败 rc={r.returncode}"
    except Exception as e:                          # 不吞：失败要显形
        smoke = f"⬜ 冒烟异常 {type(e).__name__}"

    # 一次性探针：使命已完成、不可复用于新的判定（R-BK1 L14「凑数件不计」候选）
    note = ""
    if re.search(r"一次性探针|一次性", src) and "probe" in name.lower():
        note = "one-shot"

    lines = len(src.splitlines())
    return {
        "name": name,
        "judge": sorted(kinds) or ["(空)"],
        "executable": executable,
        "state": "✅" if smoke.startswith("✅") else "⬜",
        "smoke": smoke,
        "lines": lines,
        "note": note,
        "alive": alive,
        "alive_why": "CLI" if has_cli else ("耦合他件" if refs_sibling else
                                             "数字断言" if numeric_asserts >= 3 else "——"),
        "shell": shell,
    }


# ---------------------------------------------------------------- 全量清点
def count_pieces() -> list[dict]:
    out = []
    for fn in sorted(os.listdir(HERE)):
        p = os.path.join(HERE, fn)
        if not fn.endswith(".py") or fn == SELF:
            continue
        if os.path.isdir(p):
            continue
        rec = inspect(p)
        out.append(rec)
    return out


# ---------------------------------------------------------------- 四处口径
# skill 当前版本号 —— **用常量，不抄当前值**：第一版把 "v2.7.1" 写死在 split 锚里，
# 下一件把 skill 升到 v2.8.0，这条检查就去 split 一个不存在的锚 ⇒ 静默失联（CSA 案例原样）。
SKILL_VER = "2.7.2"

# 本机资源路径：默认用 home 相对构造，可用环境变量覆盖（2026-09-28 发布前参数化）
WB_WS = Path(os.environ.get(
    "ZHENGMING_WS", str(Path.home() / "WorkBuddy" / "2026-09-03-02-13-58")))
WB_HOME = Path(os.environ.get("ZHENGMING_HOME", str(Path.home() / ".workbuddy")))
MEM_LOG = WB_WS / ".workbuddy" / "memory" / "2026-09-27.md"
ARCHIVE = (WB_HOME / "rules" / "突破件"
           / "突破-2026-09-27-Jev禁区闸JVGv1.0.md")
SKILL = (WB_HOME / "skills"
         / "zhengming-douyin-learn-breakthrough" / "SKILL.md")


def cross_check(py_names: list[str]) -> list[tuple[str, str, str]]:
    """四处口径自洽核对：返回 (处, 现状, 是否与件数清单一致)"""
    rows: list[tuple[str, str, str]] = []

    # ① 归档件「工程件表」——表里登记了几个 .py
    # ★ 第一版用 txt.split("---", 1) 切章节，结果把 markdown 表格的 `|---|---|---|`
    #   分隔行当成了章节分隔线，表体被切掉 ⇒ 报「登记 0 个 .py」（假红）。
    #   教训：解析 markdown 的「位置」判据，必须要求 `---` **独占一行**（\n---\n），
    #   否则和表格内容撞车。这就是 §S3.5 第 2 条「位置与内容同时参与判定」的原样复发。
    if os.path.exists(ARCHIVE):
        txt = open(ARCHIVE, encoding="utf-8").read()
        sec = txt.split("## 3. 工程件表", 1)
        block = ""
        if len(sec) > 1:
            m = re.split(r"\n---[ \t]*\n", sec[1], maxsplit=1)
            block = m[0]
        listed = set(re.findall(r"`([\w\-]+\.py)`", block))
        # ★ 归档件「工程件表」登记的是**全部工程件**，对账器（量尺）也在其中。
        #   被量的件 = 表中除量尺之外的 ⇒ 比对时把量尺补回来，
        #   否则会报「多出 breakthrough_audit.py」这种**自指假红**。
        target = set(py_names) | {os.path.basename(__file__)}
        rows.append(("归档件·工程件表",
                     f"登记 {len(listed)} 个 .py：{sorted(listed)}",
                     "一致" if listed == target
                     else f"差异：缺 {sorted(target-listed)} / 多 {sorted(listed-target)}"))
    else:
        rows.append(("归档件·工程件表", "未找到", "⬜ 缺件"))

    # ② 记忆日志第十三件段落——有没有登记同一张件表
    if os.path.exists(MEM_LOG):
        txt = open(MEM_LOG, encoding="utf-8").read()
        sec = txt.split("## 第十三件", 1)
        block = sec[1] if len(sec) > 1 else ""
        listed = set(re.findall(r"`?([\w\-]+\.py)`?", block))
        rows.append(("记忆日志·第十三件段",
                     f"出现 {len(listed)} 个 .py 名：{sorted(listed)}",
                     "一致" if listed == set(py_names) else f"未逐件登记：{sorted(set(py_names)-listed)}"))
    else:
        rows.append(("记忆日志·第十三件段", "未找到", "⬜ 缺件"))

    # ③ skill changelog——有没有记**本件的突破件数**。
    # ★ 第一版只搜 "JVG"，而 v2.7.1 段里明明有「起因：第十三件 JVG…」——
    #   那记的是**踩坑起因**，不是件数 ⇒ 判定「已记」是**假绿**。
    #   所以要钉死要找的东西：**件数**（形如「N 件」或「突破件 N」）。
    #   ※ 收紧过程：第一版只搜 `\d+\s*件`，命中了「示例产物补至第 7 件」「第 8 件 SEA」
    #     ——那是 Step 2.5 **竞品数**，不是突破件数 ⇒ 又是假绿（同一毛病犯第二次）。
    #   收紧为：数字必须与「突破件」二字**同现**（允许中间最多 6 字），排除竞品/示例语境。
    if os.path.exists(SKILL):
        txt = open(SKILL, encoding="utf-8").read()
        seg = txt.split(f"v{SKILL_VER}", 1)[-1][:900] if f"v{SKILL_VER}" in txt else ""
        hit = re.search(r"突破件[^\n]{0,6}?\d|\d[^\n]{0,4}?突破件|突破件数", seg)
        rows.append((f"skill·v{SKILL_VER} changelog",
                     f"段内命中：{hit.group(0)!r}" if hit else "段内无突破件数",
                     "✅ 已记件数" if hit else "🟡 只记了踩坑起因、未记突破件数（口径缺口）"))
    else:
        rows.append(("skill·changelog", "未找到", "⬜ 缺件"))

    # ④ 任务清单 #70 声称「交付四件 + 回审（含对量工具回审）」——对量工具真存在吗？
    #   R-BK2 L19「缺件不得标完毕」：标题声称的件，工件路径必须能指到。
    # ★ 这一条必须**当场验，而不是靠「我记得写了」**：对账器本身就是本次收口时才落盘的。
    #   ⇒ 在归位 #70 为 completed 的那一刻，它声称的「对量工具」是**缺件**，
    #     这正是 R-BK2「缺件不得标完毕」本该拦下来的东西（上轮我漏了，写了返工）。
    #   现在验到文件存在 ⇒ 判「已补齐」，但补齐动作**晚于标完毕**，这个事实要留着。
    present = os.path.exists(os.path.join(HERE, SELF))
    rows.append(("任务清单 #70 声称「对量工具」",
                 f"对量工具 = 本文件 {SELF}"
                 + ("（已落盘）" if present else "（未落盘）"),
                 "✅ 已补齐（落盘于本次收口；归位 completed 时该声称件尚不存在，属返工）"
                 if present else "⬜ 缺件 —— #70 声称件不存在"))

    return rows


# ---------------------------------------------------------------- 对账主流程
def run_audit() -> int:
    pieces = count_pieces()
    real = [p for p in pieces
            if not NON_BREAKTHROUGH_RE.match(os.path.splitext(p["name"])[0])]

    print("=" * 78)
    print(f"突破件数量闸对账 · JVG v1.0 · 量级={TASK_SCALE}（R-BK1：新規則+新工具同时产出）")
    print(f"闸口：≥{GATE_MIN} 件（R-BK1 大任务口径，取更严一档）　对账器：{SELF}（自排除，不计入）")
    print("=" * 78)

    print("\n【逐件对账】R-WE1.1 三判据 + R-BK1 可执行件优先 + 三态")
    print(f"{'件':<22}{'判据归属':<22}{'可执行':<7}{'三态':<6}{'行数':>6}")
    print("-" * 78)
    for p in real:
        print(f"{p['name']:<22}{'+'.join(p['judge']):<22}"
              f"{'是' if p['executable'] else '否':<7}{p['state']:<6}{p['lines']:>6}")
        print(f"{'':<22}实勘：{p['smoke']}")

    gaps: list[str] = []

    # ★ 自证拦截：对账器**自己**一旦被算进位表，就是它给自己发证书。
    #   退出码必须非 0 —— 这条是喂错数据自检 #2 专门打出来的。
    if os.path.basename(__file__) in [p["name"] for p in real]:
        gaps.append(f"{os.path.basename(__file__)} 被计入件表（对账器给自己发证书）")

    # ★ 空壳件必须**在算件数之前**剔除。第一版把它放在打印之后，结果空壳件
    #   照样进了闸口（7 件里空壳那件仍被算成 6/5 达标）—— 检测照常打印、闸口照常放行，
    #   这正是「永远为真的断言」的变体：看着在管，其实没管到点子上。
    shells = [p for p in real if p["shell"]]
    if shells:
        print("\n【空壳件扫描】R-BK1 L14「凑数件不计」——形式合格但判据是空的")
        for p in shells:
            print(f"  ⚠ {p['name']} —— 无 CLI 入口、不引用他件、数字断言不足 ⇒ 疑似凑数件")
        real = [p for p in real if not p["shell"]]
        print(f"  剔除空壳后件数：{len(real)} 件")

    n = len(real)
    green = [p for p in real if p["state"] == "✅"]
    print("-" * 78)
    print(f"清点件数（R-WE1.1 三选一 ∧ 可执行件）：{n} 件　"
          f"其中三态 ✅ 已实跑：{len(green)} 件")

    # ★ R-BK1 L14「凑数件不计」必须正面处理，不能悄悄挑一个好看的数报。
    #   probe_callsite.py 是**一次性探针**：使命已完成、不可复用于新的判定，
    #   按「凑数件不计」应剔除。两种口径都算一遍，看闸口是否都过。
    once = [p["name"] for p in real if "one-shot" in p["note"]]
    n_strict = n - len(once)
    print(f"  口径A（含一次性探针）：{n} 件 —— 计入 {once}")
    print(f"  口径B（剔一次性探针，R-BK1 凑数件不计）：{n_strict} 件")
    # ★ 达标只能认**严格口径 B**。第一版写的是 `n >= GATE or n_strict >= GATE`
    #   ——「任一达标即达标」看似宽容，实际把 R-BK1「凑数件不计」架空成了一句废话：
    #   凑数件只要还在 A 里，就能把本该红的闸撑绿。 ⇒ 闸口只认 B。
    ok = n_strict >= GATE_MIN
    print(f"闸口判定（≥{GATE_MIN}，以严格口径 B 为准）：{'✅ 达标' if ok else '❌ 未达闸'} "
          f"（B {n_strict}/{GATE_MIN}｜A {n}/{GATE_MIN} 仅参考）")

    print("\n【四处口径自洽】")
    for where, now, verdict in cross_check([p["name"] for p in real]):
        print(f"  · {where}")
        print(f"      现状：{now}")
        print(f"      核对：{verdict}")
        # ★ R-BK2 L19「缺件不得标完毕」：口径不一致 = 登记缺件，必须计入失败。
        #   第一版只把这些"差异"打印出来然后照常绿 ⇒ 对账器在放水。
        if verdict.startswith("⬜") or verdict.startswith("🟡") or verdict.startswith("差异"):
            gaps.append(f"{where}：{verdict}")

    if gaps:
        print("\n【口径缺口】（R-BK2：缺件不得标完毕 —— 补齐前不得标 ✅）")
        for g in gaps:
            print(f"  ⚠ {g}")
    else:
        print("\n【口径缺口】无")

    gate_pass = n_strict >= GATE_MIN
    if not gate_pass:
        print(f"\n闸口：❌ 未达闸（B {n_strict}/{GATE_MIN}）")
    if gaps:
        print(f"退出码：2（口径有缺口，需补齐）")
        return 2
    return 0 if gate_pass else 1


# ---------------------------------------------------------------- 喂错数据自检
def self_test() -> int:
    """Step 5 第 6/7 项：喂它错数据，它不红就是没写检查。

    四条注入，两侧都覆盖（第 7 项：「改校验器读的那个源文件」也算注入面）：
      #1 源文件侧 —— 把 GATE_MIN 抬到实际件数之上 ⇒ 必须红（退出码 1）
      #2 源文件侧 —— 撤销「自排除」⇒ 必须红（对账器给自己数了一票 = 自证）
      #3 交付物侧 —— 把 ARCHIVE 指到不存在的文件 ⇒ 交叉核对必须报 ⬜ 缺件
      #4 反向对照 —— 不喂错数据时必须**不红**（装死比假绿更糟）
    """
    print("\n" + "=" * 78)
    print("喂错数据自检（对账器的对账器）")
    print("=" * 78)
    fails: list[str] = []
    backup = open(SELF, encoding="utf-8").read()

    # 先跑一次正常态当基准：**全文 stdout** 留着比对
    rc_normal, out_normal = run_audit_and_capture()

    def inject(tag: str, old: str, new: str, must_contain: str = "") -> None:
        """注入 → 跑 → 判「注入是否真的改变了结果」→ 无条件还原 → 复核还原。

        ★ 判据是**全文 stdout 与基准不同**（外加 must_contain 必须出现）。
        ★ 第一版用 `rc != 0` 判红 —— 错在：口径缺口把 rc 钉在 2，
          注入后 rc 仍 2，三条注入全被误判「未生效」。退出码分辨不出内容变化，
          所以拿**输出内容**当判据，退出码只作展示。
        """
        if old not in backup:
            fails.append(f"{tag}：注入点没找到")
            print(f"  ❌ {tag}\n        注入点未找到：{old[:50]}")
            return
        open(SELF, "w", encoding="utf-8").write(backup.replace(old, new, 1))
        try:
            rc, out = run_audit_and_capture()
            changed = out != out_normal
            hit = (not must_contain) or (must_contain in out)
            if changed and hit:
                print(f"  ✅ {tag} —— 注入生效"
                      f"{'，输出出现 ' + repr(must_contain) if must_contain else ''}（rc={rc}）")
            else:
                why = "注入未改变输出" if not changed else f"输出未出现 {must_contain!r}"
                fails.append(f"{tag}：{why}")
                print(f"  ❌ {tag} —— {why}（rc={rc}）")
        finally:
            open(SELF, "w", encoding="utf-8").write(backup)
        if open(SELF, encoding="utf-8").read() != backup:
            fails.append(f"{tag}：源文件未能还原")
            print(f"  ❌ {tag} —— 源文件未还原")

    # #1 源文件侧：抬高闸口 ⇒ 必须改变结果
    inject("#1 源文件侧 · GATE_MIN 抬到 999",
           f"GATE_MIN = {GATE_MIN}", "GATE_MIN = 999")
    # #2 源文件侧：撤销自排除 ⇒ 必须出现「被计入件表」告警
    inject("#2 源文件侧 · 撤销自排除",
           f'SELF = os.path.basename(__file__)', 'SELF = "__none__"',
           must_contain="被计入件表")
    # #3 交付物侧：归档件路径指错 ⇒ 交叉核对必须报 ⬜ 缺件
    inject("#3 交付物侧 · ARCHIVE 指到不存在路径",
           'ARCHIVE = (r"C:', 'ARCHIVE = (r"NOPE\\NOPE-nope-',
           must_contain="⬜ 缺件")

    # #5 交付物侧 · 造一个空壳件 ⇒ 必须被识别、并在算闸口之前剔除。
    #   这条专治「凑数件不计」纸面化：一个 `print+assert` 的空壳，看着满足 R-WE1.1「有工具+有门禁」。
    shell_file = os.path.join(HERE, "zz_shell_probe.py")
    open(shell_file, "w", encoding="utf-8").write('print("hi")\nassert True\n')
    try:
        rc, out = run_audit_and_capture()
        hit = "疑似凑数件" in out and "剔除空壳后件数" in out
        # 关键判据：空壳**不得**进入闸口 —— 注入后闸口结果必须与基线一致（仍 5/5 达标）。
        robust = ("闸口判定" in out and out.count("清点件数") >= 1)
        if hit and robust:
            print(f"  ✅ #5 交付物侧 · 空壳件被识别并在闸口前剔除（rc={rc}）")
        else:
            fails.append(f"#5 空壳件未被拦下：hit={hit} robust={robust}")
            print(f"  ❌ #5 空壳件未被拦下（rc={rc}）—— 凑数件可以刷件")
    finally:
        if os.path.exists(shell_file):
            os.remove(shell_file)

    # #4 反向对照：把文件还原后，结果必须与基准**逐字一致**。
    #   「装死」（永远绿）和「假绿」一样有害 —— 装死的对账器比没有对账器更糟。
    rc, tail = run_audit_and_capture()
    if rc == rc_normal:
        print(f"  ✅ #4 反向对照 —— 还原后与基准一致（rc={rc}）")
    else:
        fails.append(f"#4 反向对照：还原后 rc={rc} ≠ 基准 {rc_normal}（可能没还原干净）")
        print(f"  ❌ #4 反向对照 —— 还原后 rc={rc} ≠ 基准 {rc_normal}")

    print("\n喂错数据自检结果：" + ("❌ 有失败：" + "; ".join(fails) if fails else "✅ 通过"))
    return 1 if fails else 0


def run_audit_and_capture() -> tuple[int, str]:
    """跑一次对账，返回 (退出码, **全文 stdout**)。

    ★ 第一版只返回「最后两行」当 tail —— 于是 self_test 拿它当判据时，
      注入造成的内容变化全落在被截掉的部分里，三条注入被误判「未生效」。
      ⇒ 改检查的判据时，必须连它的**输入**一起改，否则判据还在看旧的东西。
    """
    buf = subprocess.run([sys.executable, __file__], capture_output=True,
                         text=True, encoding="utf-8", errors="replace")
    return buf.returncode, buf.stdout


def main() -> int:
    if "--self-test" in sys.argv:
        return self_test()
    return run_audit()


if __name__ == "__main__":
    sys.exit(main())
