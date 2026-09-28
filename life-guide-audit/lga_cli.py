#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LGA — Life-Guide Audit（生活指南可执行性审计器）v1.0

第九件突破件 · 抖音《当代年轻人的齐民要术》(#生活指南 #github #开源项目)

一句话定位：
    这个赛道所有人都在回答「该怎么做」，没有一个人回答「我做对了没有，这条建议还鲜不鲜」。
    LGA 把后者变成可跑的度量。

两种模式：
    list-verify  二手清单逐条核真（治「引用未核实的中间物」这个病）
    audit        单仓库 Markdown 条目级审计（可执行性 / 判据缺失 / 保鲜度 / 闭环率）

诚实声明：
    本工具的策略是**启发式**，阈值未标定，属于工程取值而非科学结论。
    它度量的是「文本像不像可执行」，不是「这条建议对不对」。别混用。
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import subprocess
import sys
from typing import Any
from urllib.parse import urlencode

# ---------------------------------------------------------------- 退出码口径

EXIT_OK = 0
EXIT_FAIL = 1
EXIT_WARN = 2

# 「可以直接拿去用」的结论档。其余一律告警退出（口径同 SEA，见 sea_cli.scene_exit_code）。
_USABLE_VERDICTS = {"ok", "mixed", "caution"}


def lga_exit_code(res: Any) -> int:
    """audit 模式的退出码（可单测）。与 SEA 同一套语义，方便串在 CI 里。"""
    return EXIT_OK if res.get("verdict") in _USABLE_VERDICTS else EXIT_WARN


def list_verify_exit_code(res: Any) -> int:
    """
    list-verify 模式的退出码。**不能套用 lga_exit_code。**

    理由：audit 里 mixed = "结论可用、参半正常"；但 list-verify 里 mixed = "我抓到存疑条目了"。
    两者字面 alike、含义相反，共用一套码会让"核真发现 3 条错路径"静默退出 0。
    清单核真的全部意义就是挑错，所以只要 suspect > 0 就必须停。
    """
    return EXIT_OK if res.get("suspect", 0) == 0 else EXIT_WARN


# ---------------------------------------------------------------- 启发式词典

# 动作动词表：命中 = 这条像在让人做某件事。
ACTION_VERBS = [
    "打开", "注册", "申请", "下载", "安装", "查询", "拨打", "核对", "保存", "备份",
    "设置", "添加", "修改", "联系", "预约", "提交", "比对", "测量", "记录", "验证",
    "测试", "停用", "注销", "登录", "导出", "打印", "复印", "转账", "缴费", "报名",
    "确认", "检查", "核对", "走", "办", "拿", "取", "寄", "存", "换成", "下载",
    "打开", "关掉", "屏蔽", "开启", "选择", "填写", "上传", "截图", "留档",
]
_ACTION_RE = re.compile("|".join(re.escape(v) for v in ACTION_VERBS))

# 判据信号：命中 = 这条给了「做到什么程度算对」。
_CRITERIA_PATTERNS = [
    r"如果", r"若.{0,4}则", r"否则", r"一旦", r"当.{0,6}时",
    r">=", r"<=", r"≥", r"≤", r"→", r"=>",
    r"大于", r"小于", r"超过", r"低于", r"不少于", r"不多于",
    r"\d+\s*(分|天|次|元|块|%|岁|小时|分钟|GB|g)",
    r"达标", r"不合格", r"不符合", r"异常", r"正常", r"报错",
    r"上限", r"下限", r"阈值", r"标准", r"条件",
    r"判断", r"看.{0,4}是否", r"自检",
]
_CRITERIA_RE = re.compile("|".join(_CRITERIA_PATTERNS))

# 保鲜信号：命中 = 这条依赖外部事实，过期就会骗人。
_FRESHNESS_PATTERNS = [
    r"https?://", r"\d+\s*元", r"¥\s*\d+", r"￥\s*\d+",
    r"\d{4}\s*年", r"v?\d+\.\d+", r"^\s*#",
    r"新政|新规|新政策|通知|条例|规定|办法",
    r"官网|公众号|小程序|APP|SDK",
    r"最新版|当前版本",
]
_FRESHNESS_RE = re.compile("|".join(_FRESHNESS_PATTERNS), re.MULTILINE)

# 裸话信号：命中 = 只有形容词，没有动作也没有对象。
_VAGUE_HINTS = ["要注意", "要注意的", "建议", "应该", "合理", "适度", "尽量", "酌情", "看情况"]

_ITEM_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(?=\S)")
_LIST_PREFIX_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(?=\S)")
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")


# ---------------------------------------------------------------- 文本切条

def strip_fences(text: str) -> str:
    """
    去掉围栏代码块——代码块整段示例，不该被当成指南条目。

    坑（v1.0 第一版就栽在这）：围栏也可能开在列表项里，形如 "- ```python"。
    若只看行首，这行认不出围栏，于是它之后的条目全被当成"围栏内"吞掉。
    所以判定时要把列表前缀剥掉再看内容。
    """
    out: list[str] = []
    in_fence = False
    for line in text.splitlines():
        content = _LIST_PREFIX_RE.sub("", line)
        if _FENCE_RE.match(content):
            in_fence = not in_fence
            continue
        if not in_fence:
            out.append(line)
    return "\n".join(out)


def _has_object(text: str) -> bool:
    """粗判「有没有说到一件事」。纯动词短语或纯形容词都不算。"""
    body = re.sub(r"[^\w\u4e00-\u9fff]+", " ", text)
    # 去掉动作动词后剩余长度 ≥2 且含中文 -> 认为有对象
    residual = _ACTION_RE.sub(" ", body)
    return len(residual.strip()) >= 2 and bool(re.search(r"[\u4e00-\u9fff]{2,}|[A-Za-z]{2,}", residual))


_CHECKBOX_RE = re.compile(r"^\s*(?:[-*+]\s+|(?:\d+[.)]\s+)?)\[([ xX])\]\s*(?=\S)")


def extract_items(md_text: str) -> list[dict[str, Any]]:
    """
    把 Markdown 切成条目。
    列表项 = 条目；标题只作为上下文挂到后续条目上，不计入条目数。

    复选框要分两态：
      "- [ ] 核对房东身份证"  -> 未勾选，是**给读者的建议**
      "- [x] 增加新版序言"    -> 已勾选，是**作者自己的更新记录**，不是建议
    把已勾选项混进分母，会让可执行率被更新日志压平（第一版就吃到这个亏）。
    """
    items: list[dict[str, Any]] = []
    section = ""
    for raw in strip_fences(md_text).splitlines():
        head = _HEADING_RE.match(raw)
        if head:
            section = raw.strip().lstrip("#").strip()
            continue
        body = raw.strip()
        if not _ITEM_RE.match(body):
            continue
        cb = _CHECKBOX_RE.match(body)
        items.append({
            "text": _CHECKBOX_RE.sub("", body).strip() if cb else body,
            "section": section,
            "checked": bool(cb and cb.group(1).lower() == "x"),
        })
    return items


# ---------------------------------------------------------------- 打分

def score_item(item: dict[str, Any], verbose: bool = False) -> dict[str, Any]:
    text = item["text"]
    has_verb = bool(_ACTION_RE.search(text))
    has_obj = _has_object(text)
    has_criteria = bool(_CRITERIA_RE.search(text))
    actionable = has_verb and has_obj
    closure = actionable and has_criteria
    vague_only = (not actionable) and any(h in text for h in _VAGUE_HINTS)

    return {
        "section": item["section"],
        "text": text[:120],
        "has_verb": has_verb,
        "has_object": has_obj,
        "has_criteria": has_criteria,
        "actionable": actionable,
        "closure": closure,
        "vague_only": vague_only,
        # 已勾选的复选框是作者的事记，不是给读者的建议，单独归类
        "is_meta": bool(item.get("checked")),
        "freshness_signal": bool(_FRESHNESS_RE.search(text)),
    }


# ---------------------------------------------------------------- GitHub 取数

def _gh_api(path: str, params: dict[str, str] | None = None) -> Any:
    """
    走 gh CLI，复用既有凭据，不在代码里落任何 token。

    坑（v1.0 真踩到）：`gh api -f key=value <endpoint>` 对 git/trees 这类端点
    不生效，会老老实实 404；改成查询串 `?key=value` 就通。本工具只发 GET，
    所以一律拼查询串，不用 -f。
    """
    url = path
    if params:
        url = f"{path}?{urlencode(params)}"
    cmd = ["gh", "api", "--jq", ".", url]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return {"_error": str(exc)}
    if p.returncode != 0:
        return {"_error": (p.stderr or p.stdout or "gh api failed").strip()[:200]}
    try:
        return json.loads(p.stdout)
    except json.JSONDecodeError:
        return {"_error": "non-json response"}


def _get_json(url_path: str, params: dict[str, str] | None = None) -> Any:
    return _gh_api(url_path, params)


def _branch_of(repo: str) -> str | None:
    data = _get_json(f"repos/{repo}")
    if "_error" in data:
        return None
    return data.get("default_branch")


def _resolve_branch(repo: str) -> str | None:
    """
    确定该读哪个分支。

    坑（v1.0 真踩到）：GitBook 系老仓库默认分支是 master，
    此时裸 `git/trees` 端点会 404，必须显式把分支名带进路径。
    反过来，也有默认分支是 main 却仍 404 的，所以这里带回退链。
    """
    if repo not in _BRANCH_CACHE:
        b = _branch_of(repo)
        _BRANCH_CACHE[repo] = b or "main"
    return _BRANCH_CACHE[repo]


_BRANCH_CACHE: dict[str, str] = {}


def _fetch_file(repo: str, path: str) -> str | None:
    data = _get_json(f"repos/{repo}/contents/{path}")
    if "_error" in data or "content" not in data:
        return None
    try:
        return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    except Exception:
        return None


def list_markdown(repo: str, max_files: int = 20) -> list[str]:
    branch = _resolve_branch(repo)
    tried: list[str] = []
    for ref in ([branch] if branch else []) + ["main", "master"]:
        if ref in tried:
            continue
        tried.append(ref)
        data = _get_json(f"repos/{repo}/git/trees/{ref}", {"recursive": "1"})
        if "_error" not in data and "tree" in data:
            paths = [t["path"] for t in data.get("tree", [])
                     if t.get("path", "").lower().endswith(".md")]
            return paths[:max_files]
    return []


# ---------------------------------------------------------------- 模式一：清单核真

def _star_ok(claimed: Any, actual: int | None, tol_pct: float = 0.10) -> bool:
    if not claimed or actual is None:
        return False
    try:
        c = float(claimed)
    except (TypeError, ValueError):
        return False
    if c <= 0:
        return actual > 0
    return abs(c - actual) / c <= tol_pct


def verify_list(entries: list[dict[str, Any]], star_tol_pct: float = 0.10) -> dict[str, Any]:
    """
    逐条核真二手清单。

    治什么病：拿一个聚合站的清单当证据源，结果 owner 路径是错的、
    星数是三年前的数、仓库已经 archived——引用的人不知道，LGA 让它知道。
    """
    results = []
    for ent in entries:
        rec: dict[str, Any] = {
            "claimed": ent.get("name") or ent.get("repo") or ent.get("url", ""),
            "claimed_star": ent.get("star"),
            "claimed_url": ent.get("url", ""),
            "status": "error",
            "actual_star": None,
            "actual_path": None,
            "archived": None,
            "pushed": None,
            "note": "",
        }
        slug = ent.get("repo") or ent.get("name") or ""
        slug = slug.strip().rstrip("/").replace("https://github.com/", "")
        slug = slug.split("#")[0].strip()

        if not slug:
            rec["note"] = "条目里没有可用仓库标识"
            results.append(rec)
            continue

        data = _get_json(f"repos/{slug}")
        if "_error" not in data and "full_name" in data:
            rec.update({
                "status": "match" if _star_ok(rec["claimed_star"], data.get("stargazers_count"), star_tol_pct) else "star_mismatch",
                "actual_star": data.get("stargazers_count"),
                "actual_path": data.get("full_name"),
                "archived": data.get("archived"),
                "pushed": (data.get("pushed_at") or "")[:10],
            })
            if rec["status"] == "star_mismatch":
                rec["note"] = "路径对得上，但星数与清单不符（清单过期或数错了）"
            elif data.get("archived"):
                rec["status"] = "archived"
                rec["note"] = "路径可用，但仓库已归档，指南大概率已停止维护"
            results.append(rec)
            continue

        # 404 —— 先别急着判死，可能是清单把 owner 写错了
        hits = _get_json("search/repositories", {"q": slug.split("/")[-1] + " in:name", "per_page": "5"})
        cands = []
        if isinstance(hits, dict) and "items" in hits:
            for it in hits["items"]:
                cands.append({
                    "full_name": it.get("full_name"),
                    "stars": it.get("stargazers_count"),
                    "created": (it.get("created_at") or "")[:10],
                    "desc": (it.get("description") or "")[:70],
                })
        rec["status"] = "not_found"
        rec["note"] = "清单给的 owner/路径在 GitHub 上取不到"
        rec["candidates"] = cands
        results.append(rec)

    bad = [r for r in results if r["status"] != "match"]
    return {
        "mode": "list-verify",
        "total": len(results),
        "matched": len(results) - len(bad),
        "suspect": len(bad),
        "results": results,
        "verdict": "ok" if not bad else "mixed",
    }


# ---------------------------------------------------------------- 模式二：内容审计

def summarize(scored: list[dict[str, Any]], n_files: int = 0,
              n_files_external: int = 0) -> dict[str, Any]:
    """
    统计口径（纯函数，不碰网络 —— 这样每个数都能被断言锁住）。

    分母只算 advice（未勾选条目）。已勾选的复选框是作者事记，混进分母会
    把可执行率压平。

    阈值 0.50 / 0.20 是**工程取值，未标定**：它们度量「文本像不像可执行」，
    不度量「这条建议对不对」。写进公开材料时必须带上这句。
    """
    total = len(scored)
    if total == 0:
        return {"verdict": "degenerate", "n_items": 0, "n_meta": 0, "n_advice": 0,
                "n_actionable": 0, "n_closure": 0, "actionability": 0.0,
                "closure_rate": 0.0, "verdict_gap": 1.0, "freshness_ratio": 0.0}

    meta = [s for s in scored if s["is_meta"]]
    advice = [s for s in scored if not s["is_meta"]]
    n = len(advice)
    if n == 0:
        return {"verdict": "degenerate", "n_items": total, "n_meta": len(meta), "n_advice": 0,
                "n_actionable": 0, "n_closure": 0, "actionability": 0.0,
                "closure_rate": 0.0, "verdict_gap": 1.0, "freshness_ratio": 0.0}

    actionable = [s for s in advice if s["actionable"]]
    closure = [s for s in advice if s["closure"]]
    vague = [s for s in advice if s["vague_only"]]

    actionability = len(actionable) / n
    closure_rate = (len(closure) / len(actionable)) if actionable else 0.0
    verdict_gap = 1.0 - closure_rate
    # 保鲜度按**文件**算，不按条目算：链接和价格多写在正文段落里，不在列表项里。
    # 第一版按条目查，结果所有仓库 freshness_ratio 恒为 0，是个假数字。

    if not actionable:
        verdict = "uninformative"
    elif closure_rate >= 0.50:
        verdict = "ok"
    elif closure_rate >= 0.20:
        verdict = "mixed"
    else:
        verdict = "caution"

    return {
        "verdict": verdict,
        "n_items": total,
        "n_meta": len(meta),
        "n_advice": n,
        "n_actionable": len(actionable),
        "n_closure": len(closure),
        "n_vague": len(vague),
        "actionability": round(actionability, 4),
        "closure_rate": round(closure_rate, 4),
        "verdict_gap": round(verdict_gap, 4),
        "freshness_ratio": round(n_files_external / n_files, 4) if n_files else 0.0,
    }


def audit_repo(repo: str, max_files: int = 20) -> dict[str, Any]:
    paths = list_markdown(repo, max_files=max_files)
    if not paths:
        return {"repo": repo, "mode": "audit", "verdict": "no_evidence",
                "error": "仓库里取不到 Markdown 文件", "files_scanned": 0, "items": []}

    scored: list[dict[str, Any]] = []
    scanned = 0
    missing = 0
    n_files_external = 0
    for p in paths:
        text = _fetch_file(repo, p)
        if text is None:
            missing += 1
            continue
        scanned += 1
        # 保鲜信号在**整文件**上判：链接/价格/政策词常出现在正文段落而非列表项里
        if _FRESHNESS_RE.search(strip_fences(text or "")):
            n_files_external += 1
        for it in extract_items(text):
            scored.append(score_item(it))

    if not scored:
        return {"repo": repo, "mode": "audit", "verdict": "degenerate",
                "error": "取到了 Markdown 但没有切出任何条目",
                "files_scanned": scanned, "files_missing": missing, "items": []}

    stats = summarize(scored, n_files=scanned, n_files_external=n_files_external)
    stats["repo"] = repo
    stats["mode"] = "audit"
    stats["files_scanned"] = scanned
    stats["files_missing"] = missing
    stats["files_total"] = len(paths)
    stats["items"] = scored
    return stats


# ---------------------------------------------------------------- CLI

def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def print_audit(res: dict[str, Any]) -> None:
    print(f"仓库       {res['repo']}")
    print(f"扫描       {res.get('files_scanned', 0)}/{res.get('files_total', 0)} 个 md"
          + (f"（{res.get('files_missing', 0)} 个取不到）" if res.get("files_missing") else ""))
    print(f"条目       {res.get('n_items', 0)}（其中已勾选项 {res.get('n_meta', 0)} 条，算作者事记不计入分母）")
    print(f"可执行     {res.get('n_actionable', 0)} 条（{_fmt_pct(res.get('actionability', 0))}）")
    print(f"闭环率     {_fmt_pct(res.get('closure_rate', 0))}（动作 + 判据）")
    print(f"判据空洞   {_fmt_pct(res.get('verdict_gap', 0))}（可执行但没有「做到什么算对」）")
    print(f"保鲜风险   {_fmt_pct(res.get('freshness_ratio', 0))} 的 md 依赖外部事实（链接/价格/政策）")
    print(f"裸话条目   {res.get('n_vague', 0)}")
    print(f"结论       {res.get('verdict')}")


def print_list_verify(res: dict[str, Any]) -> None:
    print(f"清单核真   {res['matched']}/{res['total']} 条路径与星数都对得上")
    print(f"存疑       {res['suspect']} 条")
    for r in res["results"]:
        flag = "OK " if r["status"] == "match" else "!! "
        line = (f"{flag}{r['claimed']} -> {r['status']}"
                + (f" (实际 {r['actual_path']}, {r['actual_star']}★)" if r.get("actual_path") else "")
                + (f"  {r['note']}" if r.get("note") else ""))
        print(line)
        for c in (r.get("candidates") or [])[:3]:
            print(f"        候选: {c['full_name']} | {c['stars']}★ | {c['created']} | {c['desc']}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="lga", description="LGA 生活指南可执行性审计器")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("list-verify", help="二手清单逐条核真")
    p1.add_argument("--input", required=True, help="JSON 文件：[{name,url,star}, ...]")
    p1.add_argument("--star-tol", type=float, default=0.10, help="星数允许偏差比例")
    p1.add_argument("--json", action="store_true")

    p2 = sub.add_parser("audit", help="单仓库 Markdown 条目级审计")
    p2.add_argument("--repo", required=True, help="owner/name")
    p2.add_argument("--max-files", type=int, default=20)
    p2.add_argument("--show-items", type=int, default=0, help="打印前 N 条条目")
    p2.add_argument("--json", action="store_true")

    p3 = sub.add_parser("batch", help="批量审计多个仓库")
    p3.add_argument("--repos", required=True, help="逗号分隔的 owner/name")
    p3.add_argument("--max-files", type=int, default=12)
    p3.add_argument("--json", action="store_true")

    a = ap.parse_args(argv)

    if a.cmd == "list-verify":
        try:
            with open(a.input, "r", encoding="utf-8") as fh:
                entries = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            print(f"读清单失败: {exc}", file=sys.stderr)
            return EXIT_FAIL
        res = verify_list(entries, star_tol_pct=a.star_tol)
        if not a.json:
            print_list_verify(res)
        return list_verify_exit_code(res)

    if a.cmd == "audit":
        res = audit_repo(a.repo, max_files=a.max_files)
        if a.json:
            print(json.dumps(res, ensure_ascii=False))
        else:
            print_audit(res)
            for it in res.get("items", [])[: max(a.show_items, 0)]:
                print(f"  [{it['closure'] and '闭环' or '不闭环'}] {it['text']}")
        return lga_exit_code(res)

    if a.cmd == "batch":
        repos = [r.strip() for r in a.repos.split(",") if r.strip()]
        out = []
        for r in repos:
            res = audit_repo(r, max_files=a.max_files)
            out.append(res)
            if a.json:
                continue
            print_audit(res)
            print("-" * 60)
        if a.json:
            print(json.dumps(out, ensure_ascii=False))
        else:
            print(f"批量完成 {len(out)} 个仓库")
        return EXIT_OK

    return EXIT_FAIL


if __name__ == "__main__":
    sys.exit(main())
