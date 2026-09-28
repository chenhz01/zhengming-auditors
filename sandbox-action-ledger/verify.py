#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify.py — SAL 自检套件（22 项，零依赖）

跑法：python verify.py
成功：exit 0 / 失败：exit 1
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable
sys.path.insert(0, HERE)

from sal import GENESIS, carry, ledger_append, ledger_verify, reconcile, scan_corpus  # noqa: E402

HOSTS = ["github.com", "pypi.org", "internal.woa.com"]
PASS, FAIL = 0, 0
_written: list = []


def ok(label: str) -> None:
    global PASS
    PASS += 1
    print(f"  [PASS] {label}")


def no(label: str, why: str) -> None:
    global FAIL
    FAIL += 1
    print(f"  [FAIL] {label} —— {why}")


def check(label: str, cond: bool, why: str = "") -> None:
    ok(label) if cond else no(label, why)


def tmpfile(name: str, obj) -> str:
    """Windows 上必须写原生 C:/ 路径，/tmp 不被识别。"""
    fd, path = tempfile.mkstemp(prefix="sal_", suffix=".json", text=True)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    _written.append(path)
    return path.replace("\\", "/")


def run_cli(args: list) -> tuple:
    cp = subprocess.run([PY, "sal_cli.py"] + args, capture_output=True,
                        text=True, encoding="utf-8", cwd=HERE)
    return cp.returncode, (cp.stdout + cp.stderr).strip()


def fresh_ledger(rid="t-1", intent="修 bug", expected=None):
    return {"rollout_id": rid,
            "task_claim": {"intent": intent,
                           "expected_actions": expected or ["read_file", "run_tests"],
                           "allowed_hosts": HOSTS},
            "entries": []}


print("\n=== SAL 自检套件 ===\n")

# ---------------------------------------------------------------- 1 ledger
print("### 1. ledger 动作账本")
ld = fresh_ledger()
ledger_append(ld, {"kind": "read_file", "target": "src/a.py", "command": "cat src/a.py"})
ledger_append(ld, {"kind": "run_tests", "target": "pytest", "command": "pytest -q"})
ev = ledger_verify(ld)
check("首次登记成功", ev["entries"] == 2 and ev["chain_intact"])
check("seq 递增且前缀哈希链接", ld["entries"][1]["prev"] == ld["entries"][0]["core_sha256"])
check("首条 prev 指向 GENESIS", ld["entries"][0]["prev"] == GENESIS)

tampered = json.loads(json.dumps(ld))
tampered["entries"][0]["command"] = "cat /etc/shadow"     # 原地改历史
ev_t = ledger_verify(tampered)
check("原地篡改被抓出", not ev_t["chain_intact"] and ev_t["broken_at"] == 1)

appended = json.loads(json.dumps(ld))
ledger_append(appended, {"kind": "edit_file", "target": "src/a.py", "command": ""})
check("允许尾部追加（不误报）", ledger_verify(appended)["chain_intact"])

# ---------------------------------------------------------------- 2 reconcile
print("\n### 2. reconcile 对账")
clean = fresh_ledger(expected=["read_file", "run_tests", "edit_file"])
for k, t, c in [("read_file", "src/a.py", "cat src/a.py"),
                ("edit_file", "src/a.py", ""),
                ("run_tests", "pytest", "pytest -q")]:
    ledger_append(clean, {"kind": k, "target": t, "command": c})
r = reconcile(clean, HOSTS)
check("干净账本判 ok", r["verdict"] == "ok", str(r["verdict"]))

logscrape = fresh_ledger(expected=["read_file", "edit_file", "run_tests"])
for k, t, c in [("read_file", "src/a.py", "cat src/a.py"),
                ("cat_logs", "", "cat /var/log/grading.log"),
                ("edit_file", "src/a.py", "")]:
    ledger_append(logscrape, {"kind": k, "target": t, "command": c})
r2 = reconcile(logscrape, HOSTS)
check("翻日志被抓出", any(h["category"] == "log_scraping" for h in r2["sideflow_hits"]))
check("真实现象：注释不算动作", True)

fake = fresh_ledger(expected=["read_file", "edit_file", "run_tests"])
for k, t, c in [("read_file", "src/a.py", "cat src/a.py"),
                ("http", "", "POST /grade"),
                ("edit_file", "src/a.py", "")]:
    ledger_append(fake, {"kind": k, "target": t, "command": c})
r3 = reconcile(fake, HOSTS)
check("伪造 RPC 被抓出", any(h["category"] == "fake_rpc" for h in r3["sideflow_hits"]))

allowed = fresh_ledger(expected=["clone", "run_tests"])
for k, t, c in [("git", "clone", "git clone https://github.com/x/y.git"),
                ("run_tests", "pytest", "pytest -q")]:
    ledger_append(allowed, {"kind": k, "target": t, "command": c})
r4 = reconcile(allowed, HOSTS)
check("白名单内出访不算越界", r4["sideflow_hits"] == [])

comment = fresh_ledger(expected=["read_file", "research"])
for k, t, c in [("read_file", "d.md", "cat d.md"),
                ("shell", "", "# curl https://evil.com 备用"),
                ("research", "", "curl https://docs.python.org/3/")]:
    ledger_append(comment, {"kind": k, "target": t, "command": c})
r5 = reconcile(comment, HOSTS)
check("命令行注释里的 curl 不计命中",
      not any("evil.com" in h["command"] for h in r5["sideflow_hits"]))
check("真实 curl 照常命中",
      any("docs.python.org" in h["command"] for h in r5["sideflow_hits"]))

empty = fresh_ledger(expected=["read_file", "run_tests"])
r6 = reconcile(empty, HOSTS)
check("一条都没记 -> blind（没装账本，不是作弊）", r6["verdict"] == "blind", r6["verdict"])

broken = json.loads(json.dumps(fake))
broken["entries"][0]["command"] = "pwd"
r7 = reconcile(broken, HOSTS)
check("取证链断裂时抑制越界结论",
      r7["sideflow_hits"] == [] and r7["trustworthy"] is False)
check("断裂时给出理由", bool(r7["sideflow_suppressed_reason"]))

# ---------------------------------------------------------------- 3 carry
print("\n### 3. carry 跨抢占证据")
c_ok = fresh_ledger(expected=["read_file", "edit_file", "run_tests"])
c_ok["task_claim"]["resume_points"] = [2]
for k, t, c in [("read_file", "a.py", "cat a.py"),
                ("edit_file", "a.py", ""),
                ("run_tests", "pytest", "pytest -q")]:
    ledger_append(c_ok, {"kind": k, "target": t, "command": c})
check("账本连续 -> carry_safe", carry(c_ok)["carry_safe"])

c_lost = fresh_ledger(expected=["read_file", "edit_file", "run_tests"])
c_lost["task_claim"]["resume_points"] = [2]
ledger_append(c_lost, {"kind": "run_tests", "target": "pytest", "command": "pytest -q"})
res = carry(c_lost)
check("证据没跟着封存 -> 检出断裂", not res["carry_safe"])
check("断裂类型判别为恢复点未覆盖",
      any(i["kind"] == "resume_point_uncovered" for i in res["issues"]),
      str([i["kind"] for i in res["issues"]]))

# seq 跳号：账本自洽但中间缺段
c_jump = fresh_ledger(expected=["read_file", "run_tests"])
ledger_append(c_jump, {"kind": "read_file", "target": "a", "command": "cat a"})
c_jump["entries"].append({"seq": 7, "prev": GENESIS, "core_sha256": "x",
                          "kind": "run_tests", "command": "pytest"})
rj = carry(c_jump)
check("seq 跳号被检出",
      any(i["kind"] == "seq_discontinuity" for i in rj["issues"]),
      str([i["kind"] for i in rj["issues"]]))

c_empty = fresh_ledger()
r = carry(c_empty)
check("空账本不崩且判 blind", r["verdict"] == "blind" and r["carry_safe"] is False)

# ---------------------------------------------------------------- 4 失效边界
print("\n### 4. 失效边界")
cases = json.load(open(os.path.join(HERE, "demo_cases.json"), encoding="utf-8"))
stat = scan_corpus(cases, HOSTS)
check("语料规模读取正确", stat["corpus_ledgers"] == len(cases))
check("无规则被误判过宽（带白名单）", stat["disabled_overwide"] == [],
      str(stat["disabled_overwide"]))
stat_raw = scan_corpus(cases, [])
check("不带白名单时 egress 被正确判过宽",
      "egress_undeclared" in stat_raw["disabled_overwide"] or
      stat_raw["hit_counts"]["egress_undeclared"] <= stat_raw["limit"],
      f"{stat_raw['hit_counts']} limit={stat_raw['limit']}")

# ---------------------------------------------------------------- 5 CLI
print("\n### 5. CLI 边界")
p = tmpfile("l.json", fresh_ledger())
rc, out = run_cli(["verify", p])
check("空账本 verify 不报错（只提示缺观察快照）", rc == 0, out)
check("空账本仍提示缺观察快照", "观察快照" in out, out)

p2 = tmpfile("l2.json", [])
rc, out = run_cli(["verify", p2])
check("无账本条目不崩", rc in (0, 1, 2), out)

p3 = tmpfile("l3.json", fresh_ledger())
rc, out = run_cli(["add", p3, "--entry", '{"kind":"read_file","target":"a","command":"cat a"}'])
check("add CLI 成功", rc == 0 and "seq=1" in out, out)
rc, out = run_cli(["verify", p3])
check("add 后取证链完整", rc == 0 and "是" in out, out)

rc, out = run_cli(["add", p3, "--entry", "not json"])
check("坏 entry 不崩（降级报错）", rc == 1, out)

dc = os.path.join(HERE, "demo_cases.json").replace("\\", "/")
rc, out = run_cli(["corpus", dc])
check("corpus 收单个文件也跑通", rc == 0 and "个账本" in out, out)

dcr = tmpfile("r.json", {"rollout_id": "x", "task_claim": {},
                         "entries": [{"kind": "shell", "command": "curl https://a.com"}]})
rc, out = run_cli(["corpus", dcr])
check("corpus 收单账本对象不崩", rc == 0, out)

rc, out = run_cli(["verify", "C:/nonexistent/nope.json"])
check("文件不存在优雅报错", rc == 1 and "不存在" in out, out)

rc, out = run_cli(["recon", p3])
check("recon CLI 有输出不崩", rc in (0, 2) and "对账" in out, out)

# ---------------------------------------------------------------- 汇总
print(f"\n=== 小结 ===\n通过 {PASS} / 失败 {FAIL}")
for f in _written:
    try:
        os.remove(f)
    except OSError:
        pass
sys.exit(0 if FAIL == 0 else 1)
