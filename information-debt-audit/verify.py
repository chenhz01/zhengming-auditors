#!/usr/bin/env python3
"""
IDA 自检套件（verify.py）

纪律（沿用第九件教训，2026-09-27）：
  任何校验器上线前，先喂一次错数据——**它没报错，你就没写检查。**
所以本套件里有两类测试：
  ① 正向：判据产出符合预期
  ② 反向（★）：故意造"应该报警"的场景，看它报不报
     —— 只有②存在，①才有意义。

跑法：python verify.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# 与 audit_deliverable.py 同一坑（2026-09-27 交付后回审）：手写 rsplit 切路径，
# 遇到混合分隔符的 __file__ 会少切一层。统一用 resolve().parent()。
# 这里还多了个连带责任：verify 拉起对账器时用 `HERE + "/audit_deliverable.py"` 拼路径，
# 拼出来的是混合分隔符 —— **正是这个拼接把对账器的 __file__ 变成了混合形式**，
# 于是同一个 bug 会同时从两头触发。路径一律用 Path 拼，别手搓字符串。
HERE = str(Path(__file__).resolve().parent)
sys.path.insert(0, HERE)

import ida_cli  # noqa: E402

_LINES: list[str] = []
_PASSED = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global _PASSED
    if cond:
        _PASSED += 1
        _LINES.append(f"  [PASS] {name}")
    else:
        _LINES.append(f"  [FAIL] {name}" + (f" — {detail}" if detail else ""))


# ------------------------------------------------------------------ 合成 fixture

def _rollout(*events: dict) -> str:
    """把事件包成 Codex rollout 的包装层格式。"""
    return "\n".join(json.dumps({"type": "response_item", "payload": e},
                                ensure_ascii=False) for e in events) + "\n"


def _out(call_id: str, n_tok: int, warned: bool, path: str = "") -> dict:
    warn = "Warning: truncated output (original token count: %d)\n" % n_tok if warned else ""
    head = (f"Chunk ID: 43f215\nProcess exited with code 0\n"
            f"Original token count: {n_tok}\nOutput:\n{warn}"
            f"Total output lines: 957\n")
    if path:
        head += f"reading {path}\n"
    return {"kind": "function_call_output", "call_id": call_id, "output": head + "<content>" * 50}


def _call(cid: str, args: str) -> dict:
    return {"kind": "function_call", "type": "large_output", "id": f"fc_{cid}",
            "name": "exec_command",
            "arguments": json.dumps({"cmd": args}, ensure_ascii=False)}


def _reason(text: str) -> dict:
    return {"kind": "reasoning", "text": text}


def _debt(seq: int, tokens: int, warned: bool, fp: str = "", recalled: bool = False) -> dict:
    """一条 large_output 事实。字段必须齐全 —— 缺一个键 score_session 就会 KeyError，
    而这会伪装成「没检出」，跟静默少解析是同一类故障。"""
    return {"seq": seq, "type": "large_output", "tokens": tokens, "warned": warned,
            "fingerprint": fp, "recalled": recalled}


def _term(seq: int) -> dict:
    return {"seq": seq, "type": "terminator", "terminator_kind": "task_complete",
            "tokens": 0, "warned": False, "fingerprint": "", "recalled": True}


def _done() -> dict:
    return {"type": "terminator", "kind": "task_complete", "turn_id": "t1"}


# ------------------------------------------------------------------ 测试

def test_pure_functions() -> None:
    _LINES.append("— 纯函数判据 —")

    # 1. 无截断：cited_rate 必须是 None（没测得 0），不是 0.0
    s = ida_cli.score_session([])
    check("无截断时 cited_rate 为 None（不是 0.0，避免把'没测'读成'没债')",
          s["cited_rate"] is None, f"got {s['cited_rate']!r}")
    check("无截断时 verdict = no_truncation", ida_cli.verdict_of(s) == "no_truncation")

    # 2. 知情 + 立即收工 ⇒ informed_close（不是 debt_risk）
    facts = [_debt(1, 14000, warned=True, recalled=True), _term(2)]
    s2 = ida_cli.score_session(facts)
    check("知情截断+立即收工 ⇒ informed_close（v1.1 曾误判 debt_risk）",
          ida_cli.verdict_of(s2) == "informed_close", ida_cli.verdict_of(s2))
    check("该场景 decision_gap == 1", s2["decision_gap"] == 1, str(s2["decision_gap"]))

    # 3. 不知情 + 立即收工 ⇒ debt_risk（★ 反向：必须报警）
    f3 = [_debt(1, 14000, warned=False), _term(2)]
    s3 = ida_cli.score_session(f3)
    check("★反向：不知情+立即收工 ⇒ debt_risk（证明判据不是恒不报警）",
          ida_cli.verdict_of(s3) == "debt_risk", ida_cli.verdict_of(s3))
    check("该场景 n_unwarned == 1", s3["n_unwarned"] == 1, str(s3["n_unwarned"]))

    # 4. 不知情 + 收工前充分引用 ⇒ caution（不是 debt_risk）
    # 配对（fingerprint 命中 ⇒ recalled=True）在 extract_facts 阶段完成，
    # score_session 只消费配对后的结果，这里直接给 recalled=True。
    f4 = [_debt(1, 14000, warned=False, fp="C:/x/report.log", recalled=True),
          _term(3)]
    s4 = ida_cli.score_session(f4)
    check("跟踪引用过 ⇒ n_cited == 1", s4["n_cited"] == 1, str(s4["n_cited"]))
    check("有被引用 ⇒ 不判 debt_risk", ida_cli.verdict_of(s4) != "debt_risk",
          ida_cli.verdict_of(s4))

    # 5. 退出码逐档（★ 不许用 `in (a,b)` 收宽）
    for v, want in (("ok", 0), ("no_truncation", 0), ("informed_close", 1),
                    ("caution", 1), ("debt_risk", 2)):
        got = ida_cli.ida_exit_code(v)
        check(f"退出码 {v} == {want}", got == want, f"got {got}")


def test_parsing_and_integration() -> None:
    _LINES.append("— 解析与集成 —")
    themedis = ida_cli.parse_rollout  # 占位，避免误用

    # 裸 payload（没有 type 包装层）也要能解析 —— v1.0 只认包装层，817 行只解析出 3 条
    raw = ("\n".join([
        json.dumps({"kind": "function_call_output", "call_id": "call_00_x",
                    "output": "Original token count: 20000\nWarning: truncated output\n"},),
        json.dumps({"kind": "task_complete", "type": "task_complete"}),
    ]) + "\n")
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as fh:
        fh.write(raw)
        tmp = fh.name
    try:
        p = ida_cli.parse_rollout(tmp)
        check("裸 payload 也能解析（v1.0 的静默少解析已修）", len(p["events"]) == 2,
              f"got {len(p['events'])}")
        f = ida_cli.extract_facts(p)
        n_trunc = sum(1 for x in f if x["type"] == "large_output")
        check("裸 payload 能识别出截断", n_trunc == 1, f"got {n_trunc}")
    finally:
        os.unlink(tmp)

    # 解析失败率不能静默通过
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False,
                                     encoding="utf-8") as fh:
        fh.write("not json\n{{{ broken\n")
        bad = fh.name
    try:
        r = ida_cli.audit_file(bad)
        check("坏文件仍返回结构（不崩）", isinstance(r, dict))
        check("坏文件带 parse_warning", bool(r.get("parse_warning")), str(r)[:120])
    finally:
        os.unlink(bad)


def test_cli_negative(tmpdir: Path) -> None:
    """★ CLI 级反向测试：注入一个必须报警的场景，看它退不退 2。"""
    _LINES.append("— CLI 反向测试 —")
    # 不知情截断 + 一步就收工 —— 这就是必须报警的场景
    payload = "\n".join(
        json.dumps({"type": "response_item", "payload": p}, ensure_ascii=False)
        for p in (_out("call_00_a", 20000, False, "C:/x/report.log"),
                  _call("call_00_a", "grep error C:/x/report.log"),
                  _done())) + "\n"
    fpath = tmpdir / "risk.jsonl"
    fpath.write_text(payload, encoding="utf-8")

    p = subprocess.run([sys.executable, f"{HERE}/ida_cli.py", "audit", str(fpath)],
                       capture_output=True, text=True)
    check("★注入 debt_risk 场景 ⇒ 退出码 2", p.returncode == 2, f"rc={p.returncode}")
    check("输出点名 debt_risk", "debt_risk" in (p.stdout or ""), (p.stdout or "")[:160])

    # 正向：无截断场景必须退 0，且打印里必须出现「不在适用域」
    empty = tmpdir / "clean.jsonl"
    empty.write_text(json.dumps({"type": "event_msg",
                                 "payload": {"type": "task_started"}}) + "\n",
                     encoding="utf-8")
    p2 = subprocess.run([sys.executable, f"{HERE}/ida_cli.py", "audit", str(empty)],
                        capture_output=True, text=True)
    check("无截断场景 ⇒ 退出码 0", p2.returncode == 0, f"rc={p2.returncode}")
    check("且打印明说'不在适用域'，不是假装干净",
          "不在 IDA 适用域" in (p2.stdout or ""), (p2.stdout or "")[:200])


def test_summarize_shape() -> None:
    _LINES.append("— 汇总口径 —")
    res = [
        {"score": {"n_trunc": 2, "cited_rate": 0.5, "tail_debt_ratio": 0.1,
                   "debt_tokens": 3000, "n_unwarned": 1},
         "verdict": "caution"},
        {"score": {"n_trunc": 0, "cited_rate": None, "tail_debt_ratio": 0.0,
                   "debt_tokens": 0, "n_unwarned": 0},
         "verdict": "no_truncation"},
    ]
    s = ida_cli.summarize(res)
    check("coverage 分母含全部会话", s["coverage"] == "1/2", s["coverage"])
    check("verdicts 覆盖四个态", set(s["verdicts"]) >=
          {"ok", "caution", "debt_risk", "informed_close", "no_truncation"},
          str(list(s["verdicts"])))
    empty = ida_cli.summarize([])
    check("空输入不崩且 coverage 为 0/0", empty["coverage"] == "0/0")


def test_no_tautology() -> None:
    """
    ★ 反常真断言自查（第九件 rc in (0,2) 同族病的守卫）。
    检查 verdict 分支里没有「无论什么输入都成立」的条件。
    """
    _LINES.append("— 反恒真自查 —")
    src = Path(HERE, "ida_cli.py").read_text(encoding="utf-8")
    bad = 'in (0, 2)' in src or 'in (0,2)' in src
    check("源码里没有 `rc in (0, 2)` 此类收宽的退出码断言", not bad)
    check("score_session 里没有对 n_debt 的残留引用（v1.0 字段已删）",
          "n_debt" not in src, "n_debt 仍被引用")


def test_audit_negative() -> None:
    """
    ★ 对账器负向测试（第九件最贵的一课）。
    对账器若只检查「正确数字有没有出现在手册里」，注入错值它照样报通过——
    那是**能通过的检查等于没检查**。所以必须喂一次错数据，看它抓不抓得住。
    """
    _LINES.append("— 对账器负向测试 —")
    MANUAL = Path.home() / "Desktop/成果/抖音学习突破七流程-信息债务审计器-2026-09-27.html"
    if not MANUAL.exists():
        _LINES.append("  [SKIP] 手册不在预期路径，跳过对账器负向测试")
        return
    env = {**os.environ, "IDA_NO_RECURSE": "1"}   # 防 verify → 对账 → verify 递归
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                     encoding="utf-8") as fh:
        # 注入点必须落在「合计」句里。第一版用 replace("28316", ..., 1) 只替换了
        # 第一个出现处（§二 的线索表里那句），合计句没被动 ⇒ 对账照样报通过。
        # **负向测试注入错了地方，等于没有负向测试。**
        fh.write(MANUAL.read_text(encoding="utf-8")
                 .replace("累计丢 28316 token", "累计丢 99999 token", 1))
        bad = fh.name
    # ★★ 2026-09-27 交付后回审：我为了修 HERE 路径问题，顺手把 `--html", bad` 一起
    # 删掉了 —— 于是对账器跑的是默认对准文件，负向测试退化成「跑正例」，照样绿灯。
    # **修 A 的时候删掉了 B 的凭据，而测试还在亮灯，这是最隐蔽的一种负向失效。**
    # 教训：负向测试里的每个参数都要当成待测对象，不许"顺手整理"。
    try:
        p = subprocess.run([sys.executable, str(Path(HERE, "audit_deliverable.py")),
                            "--html", bad], capture_output=True, text=True,
                           timeout=120, env=env)
        out = (p.stdout or "") + (p.stderr or "")
        check("★注入错数字 ⇒ 对账器退出码 1", p.returncode == 1, f"rc={p.returncode}")
        # ★「点名」要取**尾部**：Traceback 的根因在末尾，原来截 out[:180] 只截到
        # `sys.exit(main())` 那行，真正的 FileNotFoundError 被截掉了 ——
        # 检查器为了"显示细节"恰好切掉了它要找的证据，两头都瞎。
        check("★报错时点名是哪个数不对", "99999" in out, out[-400:] or "<空输出>")
        # ★崩溃不算抓到。上一版发现「rc=1 + Traceback」也判通过，那是假阳性：
        # 检查工具自己崩了和被检查对象有问题，输出长得一模一样，必须分得开。
        check("★报错是对账的正常输出，不是它自己崩了",
              "Traceback" not in out, out[-400:] or "<空输出>")
        # ★伴生正例对照：同一套检查对准文件必须放行，否则就是「一直报警」。
        good = subprocess.run(
            [sys.executable, str(Path(HERE, "audit_deliverable.py")),
             "--html", str(MANUAL)], capture_output=True, text=True,
            timeout=120, env=env)
        # 走 check 而不是手搓字符串：手搓的 [PASS] 行只进了分母、没进 _PASSED，
        # 自检自己就变成「永远差 1」的假象。凡是断言，只能有一条出处。
        check("★伴生正例：对准文件必须放行（防'一直报警'）", good.returncode == 0,
              (good.stdout or "")[-300:])
        # ★ 这一格曾经**静默失效**：递归防护 env 把「自检项数」的校验一起关掉，
        # 于是喂错项数也照样通过。要求：防护生效时必须**明说哪一格没查**。
        # 只改代码不够 —— 得断言那个提示真的会打印出来。
        off = subprocess.run(
            [sys.executable, str(Path(HERE, "audit_deliverable.py"))],
            capture_output=True, text=True, timeout=120, env={
                **os.environ, "IDA_NO_RECURSE": "1"})
        check("★防护关掉的那一格会明说'未被校验'，不是静默跳过",
              "未被校验" in (off.stdout or "") or
              "对账通过" not in (off.stdout or ""),
              (off.stdout or "")[-300:])
    finally:
        os.unlink(bad)


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        test_pure_functions()
        test_parsing_and_integration()
        test_cli_negative(Path(td))
        test_summarize_shape()
    test_no_tautology()
    test_audit_negative()
    print("\n".join(_LINES))
    total = sum(1 for l in _LINES if l.lstrip().startswith("[PASS") or
                l.lstrip().startswith("[FAIL"))
    print(f"\nIDA 自检: {_PASSED}/{total} 通过")
    return 0 if _PASSED == total else 1


if __name__ == "__main__":
    sys.exit(main())
