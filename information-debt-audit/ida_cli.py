#!/usr/bin/env python3
"""
IDA — Information-Debt Auditor（信息债务审计器）v1.0

对 agent 执行轨迹（rollout / transcript）做「省钱」的信息侧归因。

立论（2026-09-27 第十件 · SoL-Pi 触发）：
    SoL-Pi 这类 harness 省钱机制统一地「丢弃信息以省 token」。
    它们能算出「这次压缩回本了吗」（纯 token 经济学），
    但没有任何一项度量「被丢掉的那部分，后来有没有被欠回来」。
    SoL-Pi 的 README 承诺 evidence 仍可在本地取回 —— 但「还在」不等于「读过」。
    原始观测还在磁盘上，而模型从未 recall，在账单上是净省，在信息上是净欠。

判据（全部为纯函数，可单测）：
    1. dangling_rate   悬空句柄率 = 未被召回的大观测 / 大观测总数
    2. unpaid_index    未偿指数   = Σ 归档 token / (Σ 召回 token + 1)
    3. tail_debt_ratio 收尾债务比 = 落在最后 25% 轮次的大观测 token 占比
    4. premature_close 先斩后奏   = 有未偿债务却进入完成态的段数

用法：
    python ida_cli.py audit  <rollout.jsonl> [...]
    python ida_cli.py batch  <dir>
    python ida_cli.py audit  <rollout.jsonl> --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

# ------------------------------------------------------------------ 常量

# SoL-Pi ObservationPack 对 plain text > 10 KB 才归档。这个阈值是它的工程取值，
# 我们沿用同一量级，便于和它的触发率对照 —— 但 IDA 的阈值同样是**未标定的工程取值**
# （见 verify 里的 THRESHOLD_DISCLOSURE 断言）。别把它当成科学阈值引用。
LARGE_OBS_TOKENS = 10_000

TAIL_QUANTILE = 0.25          # 「收尾」= 最后 25% 的轮次
DECISION_GAP_RISK = 1         # 最后一笔截断离「宣布完成」≤1 步 ⇒ 债务风险
TAIL_DEBT_RISK = 0.50         # 收尾 25% 里丢掉的 token 占比过半 ⇒ 债务风险

EXIT_OK = 0
EXIT_WARN = 1
EXIT_RISK = 2

# ------------------------------------------------------------------ 轨迹解析

# Codex rollout 的函数输出头部长这样（实测，[一手]）：
#   Chunk ID: 43f215
#   Wall time: 0.8619 seconds
#   Process exited with code 0
#   Original token count: 14158
#   Output:
#   Warning: truncated output (original token count: 14158)
#   Total output lines: 957
_ORIG_TOKEN_RE = re.compile(r"Original token count:\s*(\d+)")
_TRUNC_RE = re.compile(r"Warning:\s*truncated output")
# 召回：后续工具调用里出现被截断的那条命令的片段（截断的文件路径 / call_id / 关键字）
_CALL_ID_RE = re.compile(r"call[_-]?id[\"'\s:=]+([A-Za-z0-9_\-]{6,})", re.I)


def _payload_items(obj: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """把 rollout 扁平化成 (kind, payload) 序列，容忍 payload 缺失。"""
    out: list[tuple[str, dict[str, Any]]] = []
    t = obj.get("type")
    if t in ("response_item", "event_msg"):
        p = obj.get("payload")
        if isinstance(p, dict):
            kind = p.get("kind") or p.get("type") or "message"
            out.append((str(kind), p))
    return out


def parse_rollout(path: str | Path) -> dict[str, Any]:
    """
    读一个 rollout JSONL，抽出事件序列。

    坑（v1.0 真踩到）：一行 JSON 也可能整体就是一个 payload（没有 type 包装层），
    第一版只认 `{"type": ...}` 包装，结果 817 行只解析出 3 条。
    **静默少解析 = 所有判据都拿不到证据**，而且不报错。
    所以：既收包装层，也收裸 payload（用键集合反推类型）。
    """
    path = Path(path)
    events: list[dict[str, Any]] = []
    n_lines = 0
    n_bad = 0

    with path.open("r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                n_bad += 1
                continue
            if not isinstance(obj, dict):
                continue

            if obj.get("type") in ("response_item", "event_msg") or "payload" in obj:
                for kind, p in _payload_items(obj):
                    events.append({"kind": kind, "payload": p})
            else:
                # 裸 payload：靠键反推
                k = _infer_kind(obj)
                if k:
                    events.append({"kind": k, "payload": obj})

    return {
        "file": path.name,
        "n_lines": n_lines,
        "n_bad": n_bad,
        "events": events,
    }


def _infer_kind(o: dict[str, Any]) -> str | None:
    # payload 自带 kind 是 rollout 的常态；v1.0 这里只认死几种 type 值，
    # 于是 task_complete 这类被静默丢掉 —— 判据又少一块证据，还不报错。
    kind = o.get("kind")
    if isinstance(kind, str) and kind:
        return kind
    keys = set(o.keys())
    if {"output", "call_id"} <= keys or ("type" in keys and "output" in keys):
        return "function_call_output"
    if "cmd" in keys or ("arguments" in keys and "name" in keys):
        return "function_call"
    if "type" in keys and o["type"] == "function_call_output":
        return "function_call_output"
    if "total_token_usage" in keys or "info" in keys:
        return "token_count"
    return None


_PATH_RE = re.compile(r"[A-Za-z]:[\\/][\w.\\/\-]+|(?<![\w])[\w./\-]{6,}\.(?:log|json|jsonl|md|ts|py|js|html|txt|yaml|yml)(?![\w])")


def _clip(raw: str, limit: int = 4000) -> str:
    return raw[:limit]


def extract_facts(parsed: dict[str, Any]) -> list[dict[str, Any]]:
    """
    把事件序列压成「债务事实表」。

    v1.1 重写说明（2026-09-27，第十件）：
    v1.0 在这里用「同一 call_id 事后出现 ⇒ 已偿还」来配对手柄/召回，
    真跑出来 97 个 call_id **零命中** —— 因为 Codex rollout 里
    function_call 与 function_call_output 是**成对同现**的，
    id=`fc_call_00_x` / call_id=`call_00_x` 指的是同一次调用，
    不存在「事后按 id 取回」这种动作。**语料里根本没有句柄机制。**
    所以 v1.0 的 `dangling_rate` 恒为 1.00、`unpaid_index` 恒为 14158.00 ——
    那不是发现，是**配对失效的证据**。差点当成「实测悬空率 100%」写进手册。

    换成可测的东西：**截断发生的时序** ——
    一条被截断的证据，距离「宣布完成」还有几步。
    如果最后一步的依据就是残缺证据，那才是真欠债；
    如果此后 agent 又引用了别的证据才收工，那笔债还算还得上。
    """
    facts: list[dict[str, Any]] = []
    seq = 0
    for ev in parsed["events"]:
        kind, p = ev["kind"], ev["payload"]

        if kind == "function_call_output":
            raw = p.get("output")
            raw = raw if isinstance(raw, str) else ""
            m = _ORIG_TOKEN_RE.search(raw)
            n_tok = int(m.group(1)) if m else 0
            warned = bool(_TRUNC_RE.search(raw))
            if n_tok >= LARGE_OBS_TOKENS:
                seq += 1
                # 指纹：截断文本里出现的最长路径/文件名。后续若被重新读取，
                # 同一路径必然再次出现在工具参数里。
                cands = [c for c in _PATH_RE.findall(_clip(raw, 2000)) if len(c) > 8]
                fp = max(cands, key=len) if cands else ""
                facts.append({
                    "seq": seq,
                    "type": "large_output",
                    "tokens": n_tok,
                    "warned": warned,          # harness 有没有主动告知「被截断了」
                    "fingerprint": fp,
                    "recalled": False,
                })

        elif kind == "function_call":
            args = p.get("arguments")
            text = args if isinstance(args, str) else json.dumps(args, ensure_ascii=False)
            text += " " + json.dumps(p.get("name") or "", ensure_ascii=False)
            for f in facts:
                if f["type"] == "large_output" and not f["recalled"] and f["fingerprint"]:
                    if f["fingerprint"] in text:
                        f["recalled"] = True

        elif kind in ("task_complete", "turn_aborted", "agent_message"):
            seq += 1
            facts.append({
                "seq": seq,
                "type": "terminator",
                "terminator_kind": kind,
                "tokens": 0,
                "warned": False,
                "fingerprint": "",
                "recalled": True,
            })

    return facts


# ------------------------------------------------------------------ 判据（纯函数）

def score_session(facts: list[dict[str, Any]]) -> dict[str, Any]:
    """
    单条会话的判据（纯函数，可单测）。

    v1.1 重写。v1.0 的 `unpaid_index` 已删 —— 它是配对失效造出来的假数字。
    留下四组可测的：
      n_trunc / n_cited        截断计量与被引用率
      decision_gap             最后一次截断距「宣布完成」隔了几步
      tail_debt_ratio          截断是否集中在收尾 25%
      debt_tokens              累计被丢弃的 token
    """
    debts = [f for f in facts if f["type"] == "large_output"]
    terms = [(f["seq"], f["terminator_kind"]) for f in facts if f["type"] == "terminator"]

    n_trunc = len(debts)
    n_cited = sum(1 for f in debts if f["recalled"])
    # 分母是 n_trunc；n_trunc==0 时必须是 None 而不是 0.0 —— 0.0 会被读成「没有债务」
    cited_rate = round(n_cited / n_trunc, 4) if n_trunc else None

    debt_tokens = sum(f["tokens"] for f in debts)
    warned = sum(1 for f in debts if f["warned"])

    # 判决间距：最后一次截断 与 第一个 terminator 之间隔了几步
    last_trunc_seq = max([f["seq"] for f in debts], default=None)
    first_term_seq = min([s for s, _ in terms], default=None)
    if last_trunc_seq is not None and first_term_seq is not None:
        decision_gap = first_term_seq - last_trunc_seq
    else:
        decision_gap = None

    if n_trunc:
        cut = max(f["seq"] for f in debts) - max(1, int(round(n_trunc * TAIL_QUANTILE)))
        tail_tokens = sum(f["tokens"] for f in debts if f["seq"] > cut)
        tail_debt_ratio = round(tail_tokens / (debt_tokens + 1), 4)
    else:
        tail_debt_ratio = 0.0

    # 轨迹里有没有「句柄/召回」结构。原生 Codex harness 没有，所以本语料上
    # 悬空句柄率**不可测** —— 必须显式说明，否则又是一个恒 0/恒 1 的假判据。
    handle_mechanism = any(f["type"] == "large_output" and not f["warned"] for f in facts)

    return {
        "n_trunc": n_trunc,
        "n_cited": n_cited,
        "cited_rate": cited_rate,
        "debt_tokens": debt_tokens,
        "n_warned": warned,
        "n_unwarned": n_trunc - warned,
        "decision_gap": decision_gap,
        "tail_debt_ratio": tail_debt_ratio,
        "handle_mechanism": handle_mechanism,
        "n_terminators": len(terms),
    }


def verdict_of(s: dict[str, Any]) -> str:
    """
    v1.1 三态 + 一态不可判。

    关键：n_trunc == 0 时不能说 `no_debt` 然后当「干净」看 —— 那是「没测」。
    decision_gap <= 1 才是真欠债：宣布完成时，最后一步的依据就是残缺证据。

    ⚠ 另有一条 v1.0 的错判据已删：`premature_close` 在 v1.0 里恒为真
    （条件里的 n_dangling 大于 0 只因配对失效而永远成立）。
    **永远为真的断言 = 没有断言**，与第九件那个收宽的退出码断言同族。
    """
    if s["n_trunc"] == 0:
        return "no_truncation"      # 没有截断 ⇒ 不在适用域，不是「干净」
    # 关键区分（2026-09-27 真语料实证，v1.1 误报后的修法）：
    # v1.0/v1.1 把「截断后立刻收工」一律判 debt_risk，真语料一查就是**误报** ——
    # Codex 的 Warning: truncated output 就写在输出里，agent **看得见**，
    # 它收工是知情决策，不是被蒙着干活。
    # 所以只有 harness **没告知**（n_unwarned > 0）时收工，才叫真欠债。
    if s["n_unwarned"] > 0 and (s["decision_gap"] is None
                                or s["decision_gap"] <= DECISION_GAP_RISK):
        return "debt_risk"
    if s["n_unwarned"] > 0:
        return "caution"
    if s["decision_gap"] is not None and s["decision_gap"] <= DECISION_GAP_RISK:
        return "informed_close"     # 知情收工：风险偏好问题，记账但不报警
    if s["n_cited"] < s["n_trunc"] or s["tail_debt_ratio"] > TAIL_DEBT_RISK:
        return "caution"
    return "ok"


def ida_exit_code(verdict: str) -> int:
    """
    退出码：ok/no_truncation ⇒ 0；caution ⇒ 1；debt_risk ⇒ 2。

    ⚠ `no_truncation` 必须退 0，但**打印时必须同时说明「不在适用域」** ——
    否则它看起来就像「审计通过、干净」，而实际上是「这条轨迹里没有可判的东西」。
    （与第九件 `list-verify` 的 mixed 语义相反的坑同族：字面 alike、含义相反。）
    """
    return {"ok": EXIT_OK, "no_truncation": EXIT_OK, "informed_close": EXIT_WARN,
            "caution": EXIT_WARN, "debt_risk": EXIT_RISK}.get(verdict, EXIT_WARN)


def summarize(results: list[dict[str, Any]]) -> dict[str, Any]:
    """汇总口径（纯函数）。分母是「有债务的会话」，不是全部会话 —— 见 verify 断言。"""
    with_debt = [r for r in results if r["score"]["n_trunc"] > 0]
    n = len(with_debt)
    avg = (lambda k: round(sum(r["score"][k] for r in with_debt) / n, 4) if n else 0.0)
    return {
        "n_sessions": len(results),
        "n_with_debt": n,
        "coverage": f"{n}/{len(results)}" if results else "0/0",
        "avg_cited_rate": avg("cited_rate"),
        "avg_tail_debt_ratio": avg("tail_debt_ratio"),
        "total_trunc": sum(r["score"]["n_trunc"] for r in results),
        "total_debt_tokens": sum(r["score"]["debt_tokens"] for r in results),
        "verdicts": {v: sum(1 for r in results if r["verdict"] == v)
                     for v in ("ok", "caution", "debt_risk", "informed_close",
                               "no_truncation")},
    }


def audit_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    parsed = parse_rollout(p)
    facts = extract_facts(parsed)
    sc = score_session(facts)
    rec = {"file": p.name, "n_lines": parsed["n_lines"], "n_bad": parsed["n_bad"],
           "score": sc, "verdict": verdict_of(sc)}
    if parsed["n_lines"] > 0 and parsed["n_lines"] == parsed["n_bad"]:
        rec["parse_warning"] = "该文件全部行解析失败 —— 判据没有证据支撑"
    return rec


def audit_dir(d: str | Path) -> list[dict[str, Any]]:
    dp = Path(d)
    files = sorted(dp.glob("*.jsonl"))
    if not files:
        files = sorted(dp.rglob("*.jsonl"))
    return [audit_file(f) for f in files]


# ------------------------------------------------------------------ CLI

def _print_table(results: list[dict[str, Any]]) -> None:
    hdr = (f"{'文件':<42}{'截断':>6}{'引用':>6}{'引用率':>8}{'丢tok':>10}"
           f"{'判据间距':>9}{'收尾债':>8}  {'结论':<14}")
    print(hdr)
    print("-" * len(hdr) + "  " + "-" * 14)
    for r in results:
        s = r["score"]
        gap = "-" if s["decision_gap"] is None else s["decision_gap"]
        cr = "-" if s["cited_rate"] is None else f"{s['cited_rate']:.2f}"
        print(f"{r['file'][:41]:<42}{s['n_trunc']:>6}{s['n_cited']:>6}{cr:>8}"
              f"{s['debt_tokens']:>10}{str(gap):>9}{s['tail_debt_ratio']:>8.2f}  {r['verdict']:<14}")
        if r.get("parse_warning"):
            print(f"    ⚠ {r['parse_warning']}")
        if r["verdict"] == "no_truncation":
            print("    ⓘ 无截断 ⇒ 不在 IDA 适用域，不代表干净")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="IDA — 信息债务审计器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit", help="审计一个或多个 rollout 文件")
    a.add_argument("files", nargs="+")
    a.add_argument("--json", action="store_true")

    b = sub.add_parser("batch", help="审计一个目录下的所有 jsonl")
    b.add_argument("dir")
    b.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)
    # 兜底（v1.0 第十件踩坑）：子解析器漏定义 --json 时，main() 读 a.json 会
    # AttributeError 崩掉。这是第九件 lga_cli.py 的**第一个 bug，第十件原样又犯一次**
    # —— §S3.4「同一偏差连犯两次 ⇒ 规则层升级」。以后凡加子命令，--json 一律同定义。
    want_json = bool(getattr(args, "json", False))

    if args.cmd == "audit":
        results = [audit_file(f) for f in args.files]
    else:
        results = audit_dir(args.dir)

    summ = summarize(results)
    if want_json:
        print(json.dumps({"sessions": results, "summary": summ},
                         ensure_ascii=False, indent=2))
    else:
        _print_table(results)
        print()
        print(json.dumps(summ, ensure_ascii=False, indent=2))

    # 汇总口径的退出码：只要有任何一条 debt_risk 就停
    worst = max((ida_exit_code(r["verdict"]) for r in results), default=EXIT_OK)
    return worst if summ["verdicts"]["debt_risk"] else min(worst, EXIT_WARN)


if __name__ == "__main__":
    sys.exit(main())
