#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sal_cli.py — Sandbox Action Ledger 命令行入口。

用法：
  python sal_cli.py init   <out.json> --claim '<json>'     新建空账本
  python sal_cli.py add    <ledger.json> --entry '<json>'  追加一条动作
  python sal_cli.py verify <ledger.json>                   取证链核验
  python sal_cli.py recon  <ledger.json>                   声明 vs 实际对账
  python sal_cli.py carry  <ledger.json>                   跨抢占证据核验
  python sal_cli.py corpus <dir>                           语料命中率统计

退出码：0 正常 / 1 致命错误（比如文件不存在）/ 2 有告警（账本不可信）
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from sal import (GENESIS, carry, ledger_append, ledger_verify, reconcile,
                 scan_corpus)

EXIT_OK, EXIT_WARN, EXIT_FAIL = 0, 2, 1
PY = sys.executable


def _load(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _dump(obj) -> None:
    print(json.dumps(obj, ensure_ascii=False, indent=2))


def _cmd_init(a: argparse.Namespace) -> int:
    claim = {}
    if a.claim:
        try:
            claim = json.loads(a.claim)
        except json.JSONDecodeError as e:
            print(f"[ERR] --claim 不是合法 JSON：{e}", file=sys.stderr)
            return EXIT_FAIL
    if not isinstance(claim, dict):
        print("[ERR] --claim 必须是一个 JSON 对象", file=sys.stderr)
        return EXIT_FAIL
    ledger = {"rollout_id": a.out, "task_claim": claim, "entries": []}
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    print(f"[OK] 账本已建：{a.out}（空，seq=0）")
    return EXIT_OK


def _cmd_add(a: argparse.Namespace) -> int:
    ledger = _load(a.ledger)
    try:
        entry = json.loads(a.entry)
    except json.JSONDecodeError as e:
        print(f"[ERR] --entry 不是合法 JSON：{e}", file=sys.stderr)
        return EXIT_FAIL
    if not isinstance(entry, dict):
        print("[ERR] --entry 必须是一个 JSON 对象", file=sys.stderr)
        return EXIT_FAIL
    rec = ledger_append(ledger, entry)
    with open(a.ledger, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
    print(f"[OK] 已登记 seq={rec['seq']} kind={rec.get('kind')} "
          f"core={rec['core_sha256'][:12]}")
    return EXIT_OK


def _cmd_verify(a: argparse.Namespace) -> int:
    """
    退出码只反映取证链本身（完整=0 / 断裂=2）。
    「没有观察快照」是能力边界说明，不是错误 —— 动作账本本来就不存观察结果，
    如果把这种常态也判成 warn，警告会天天响，等于没有警告。
    """
    ledger = _load(a.ledger)
    ev = ledger_verify(ledger)
    if a.json:
        _dump(ev)
        return EXIT_OK if ev["chain_intact"] else EXIT_WARN
    print(f"条目数      : {ev['entries']}")
    print(f"取证链完整  : {'是' if ev['chain_intact'] else '否'}")
    if not ev["chain_intact"]:
        print(f"断裂位置    : 第 {ev['broken_at']} 条")
    if not ev["has_text_snapshot"]:
        print("[提示] 无观察快照 —— 账本只能回答'做了什么'，"
              "回答不了'当时看到了什么'；涉及判断争议的条目需另行留证")
    return EXIT_OK if ev["chain_intact"] else EXIT_WARN


def _cmd_recon(a: argparse.Namespace) -> int:
    ledger = _load(a.ledger)
    hosts = a.host.split(",") if a.host else None
    res = reconcile(ledger, hosts)
    if a.json:
        _dump(res)
        return EXIT_WARN if res["verdict"] in ("gap", "blind", "review") else EXIT_OK
    print(f"--- 对账 {res['rollout_id']} ---")
    print(f"任务声明    : {res['handshake_claim'] or '(空)'}")
    print(f"应有动作    : {res['expected_count']} / 已记账 : {res['recorded_count']}")
    if res["unrecorded_ratio"] is not None:
        print(f"未记账率    : {res['unrecorded_ratio'] * 100:.1f}%")
    print(f"结论        : {res['verdict']}")
    if res["claimed_but_absent"]:
        print(f"声明了没记  : {res['claimed_but_absent']}")
    if res["sideflow_suppressed_reason"]:
        print(f"越界判定    : 已抑制 —— {res['sideflow_suppressed_reason']}")
    for h in res["sideflow_hits"]:
        print(f"  越界嫌疑  : seq={h['seq']} [{h['category']}] {h['command']}")
    return EXIT_WARN if res["verdict"] != "ok" else EXIT_OK


def _cmd_carry(a: argparse.Namespace) -> int:
    ledger = _load(a.ledger)
    res = carry(ledger)
    print(f"--- 跨抢占核验 ---")
    print(f"恢复点      : {res['resume_points'] or '(无)'}")
    print(f"账本条目    : {res['entries']}")
    print(f"结论        : {'证据跟着一起保住了' if res['carry_safe'] else '证据断裂'}")
    for i in res["issues"]:
        print(f"  · {i['kind']}：{i['detail']}")
    return EXIT_OK if res["carry_safe"] else EXIT_WARN


def _cmd_corpus(a: argparse.Namespace) -> int:
    # 目录和单个账本文件都要能吃（实测踩坑：只判 isdir 会把 .json 文件当路径拒掉）
    path = a.dir
    if not (os.path.isdir(path) or os.path.isfile(path)):
        print(f"[ERR] 路径不存在：{path}", file=sys.stderr)
        return EXIT_FAIL
    def _take(obj) -> list:
        """单账本对象 or 账本数组都收。"""
        if isinstance(obj, list):
            return [x for x in obj
                    if isinstance(x, dict) and "entries" in x]
        if isinstance(obj, dict) and "entries" in obj:
            return [obj]
        return []

    ledgers: list = []
    for root, _d, files in os.walk(path):
        for fn in files:
            if not fn.endswith(".json"):
                continue
            fp = os.path.join(root, fn)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    ledgers.extend(_take(json.load(f)))
            except (json.JSONDecodeError, OSError):
                continue
    stat = scan_corpus(ledgers)
    if a.json:
        _dump(stat)
    else:
        print(f"语料        : {stat['corpus_ledgers']} 个账本 / "
              f"{stat['corpus_entries']} 条动作")
        print(f"采样上限    : {stat['limit']}")
        for cat, c in stat["hit_counts"].items():
            flag = "  ⚠ 过宽，不采信" if cat in stat["disabled_overwide"] else ""
            print(f"  {cat:<18} {c}{flag}")
    return EXIT_OK


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="sal", description="沙箱行为账本 —— Agent 干了什么 vs 它声称干了什么")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init", help="新建空账本")
    sp.add_argument("out")
    sp.add_argument("--claim", default="{}", help='任务声明 JSON，如 \'{"intent":"修 bug","expected_actions":["edit_file"]}\'')
    sp.set_defaults(fn=_cmd_init)

    sp = sub.add_parser("add", help="追加一条动作")
    sp.add_argument("ledger")
    sp.add_argument("--entry", required=True,
                    help='如 \'{"kind":"tool_call","target":"run_tests","command":"pytest"}\'')
    sp.set_defaults(fn=_cmd_add)

    sp = sub.add_parser("verify", help="取证链核验")
    sp.add_argument("ledger")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=_cmd_verify)

    sp = sub.add_parser("recon", help="声明 vs 实际对账")
    sp.add_argument("ledger")
    sp.add_argument("--host", help="白名单外部主机，逗号分隔")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=_cmd_recon)

    sp = sub.add_parser("carry", help="跨 GPU 抢占证据核验")
    sp.add_argument("ledger")
    sp.set_defaults(fn=_cmd_carry)

    sp = sub.add_parser("corpus", help="语料命中率统计")
    sp.add_argument("dir")
    sp.add_argument("--json", action="store_true")
    sp.set_defaults(fn=_cmd_corpus)

    a = p.parse_args(argv)
    try:
        return a.fn(a)
    except FileNotFoundError as e:
        print(f"[ERR] 文件不存在：{e.filename}", file=sys.stderr)
        return EXIT_FAIL
    except json.JSONDecodeError as e:
        print(f"[ERR] JSON 解析失败：{e}", file=sys.stderr)
        return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
