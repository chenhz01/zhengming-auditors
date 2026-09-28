r"""FSA 语料采集器 —— 采一手工程文档落盘（Step 2.75 用）

采 5 个一手源：Atlassian 官方流式错误处理文档 / 截断静默失败长文 /
LLM 流式中断调试长文 / llm-output-guard README / 流式负载测试约束长文。

落盘闸门（上件血泪版，逐条不许省）：
  1. 空响应体 → raise，不许写空文件冒充成功
  2. 正文 <2000 字节 → 判采空并 return 3
  3. 写完回头 stat，st_size == 0 → return 4
  4. 末尾统计：0 字节文件数必须为 0，否则 return 5
  5. ROOT 必须在预期工程目录，否则 return 1

★ RA-5：通道到不了 ≠ 内容不存在。采不到的源必须在 manifest 里
  单独记 `channel_failed: true` 与真实报错，不许从记忆里补写。
"""
from __future__ import annotations

import concurrent.futures as cf
import json
import re
import ssl
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "_raw" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

SOURCES = [
    {
        "file": "corpus_atlassian_streaming_errors.md",
        "url": "https://developer.atlassian.com/platform/forge/runtime-reference/forge-llms-api-errors",
        "note": "Atlassian Forge 官方：如何判定流式响应是否完整（含 finish_reason 检测代码）",
        "insecure_tls": False,
        "expect_kw": ["Exceptions are not thrown", "finish_reason"],
    },
    {
        "file": "corpus_da_truncation_silent.md",
        "url": "https://www.digitalapplied.com/blog/agent-output-truncation-silent-failures",
        "note": "AI Agent 输出截断静默失败：检测手段分级（终态字段为主，其余为辅）",
        "insecure_tls": False,
        "expect_kw": ["cannot report that it was cut off", "Only external metadata"],
    },
    {
        "file": "corpus_devto_streaming_interrupted.md",
        "url": "https://dev.to/gwenj/streaming-interrupted-how-to-debug-successful-llm-streams-before-support-tickets-start-3fn6",
        "note": "如何调试「看起来成功」的流式响应：两种日志 event 形态对照",
        "insecure_tls": False,
        "expect_kw": ["completion_reason", "terminal"],
    },
    {
        "file": "corpus_guard_readme.md",
        "url": "https://raw.githubusercontent.com/edwinsatya/llm-output-guard/main/README.md",
        "note": "llm-output-guard：检测「返回 200 OK 但失败」的 LLM 输出（含 TRUNCATED 检测器）",
        "insecure_tls": False,
        "expect_kw": ["200 OK", "TRUNCATED"],
    },
    {
        "file": "corpus_bestaiweb_streaming_gaps.md",
        "url": "https://www.bestaiweb.ai/streaming-gaps-cold-starts-and-tool-limits-the-hard-technical-constraints-of-llm-load-testing",
        "note": "流式负载测试：REST 基准工具结构性测错事件",
        "insecure_tls": False,
        "expect_kw": ["A Stream Is Not a Response", "structurally misleading"],
    },
]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def fetch(url: str, timeout: int = 25, insecure: bool = False) -> str:
    ctx = ssl.create_default_context()
    if insecure:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        raw = r.read()
    if not raw:
        raise RuntimeError("空响应体")
    return raw.decode("utf-8", "replace")


def strip_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style).*?</\1>", " ", h)
    h = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    h = (h.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " "))
    h = re.sub(r"[ \t]+", " ", h)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def one(src: dict) -> tuple[dict, str]:
    """返回 (记录, 正文)。正文为空串即表示通道没通，不许返回假象。"""
    rec = dict(src)
    try:
        body = fetch(src["url"], insecure=src.get("insecure_tls", False))
    except Exception as e:  # noqa: BLE001 —— 通道失败要如实记账，不许吞
        rec.update(channel_failed=True, error="%s: %s" % (type(e).__name__, e),
                   bytes=0, lines=0, hits=[], kw_missing=[])
        return rec, ""
    text = body if src["file"].endswith(".md") else strip_html(body)
    rec["channel_failed"] = False
    rec["error"] = None
    rec["bytes"] = len(text.encode("utf-8"))
    rec["lines"] = text.count("\n") + 1
    rec["hits"] = [k for k in src.get("expect_kw", []) if k in text]
    rec["kw_missing"] = [k for k in src.get("expect_kw", []) if k not in text]
    return rec, text


def main() -> int:
    if ROOT.name != "flow-state-auditor":
        print("[FAIL] ROOT 不在预期工程目录: %s" % ROOT)
        return 1
    if not ART.parent.is_dir():
        print("[FAIL] 语料根目录不存在: %s" % ART.parent)
        return 1

    print("[collect] %d 个源，并发采" % len(SOURCES))
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        pairs = list(ex.map(one, SOURCES))

    manifest: list[dict] = []
    for rec, text in pairs:
        if not rec.get("channel_failed"):
            if rec["bytes"] < 2000:
                print("[FAIL] %s 正文仅 %d 字节，判采空" % (rec["file"], rec["bytes"]))
                return 3
            f = ART / rec["file"]
            f.write_text(text, encoding="utf-8")
            if f.stat().st_size == 0:
                print("[FAIL] %s 落盘后 0 字节" % rec["file"])
                return 4
        manifest.append(rec)
        flag = "FAIL" if rec.get("channel_failed") else "ok"
        print("  [%s] %-42s %7d B / %5d 行  hits=%d/%d %s"
              % (flag, rec["file"], rec["bytes"], rec["lines"],
                 len(rec["hits"]), len(rec.get("expect_kw", [])),
                 rec["error"] or ""))

    (ART / "_manifest.json").write_text(
        json.dumps({"collected_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "sources": manifest}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    zero = [m["file"] for m in manifest if not m.get("channel_failed")
            and m["bytes"] == 0]
    if zero:
        print("[FAIL] 存在 0 字节文件: %s" % zero)
        return 5

    # ★ 关键断言：招牌关键词必须命中，否则语料不是我以为的那篇
    for m in manifest:
        if m.get("channel_failed"):
            continue
        if m["kw_missing"]:
            print("[FAIL] %s 缺少预期关键词 %s —— 采到的可能不是目标页面"
                  % (m["file"], m["kw_missing"]))
            return 6

    print("[collect] 全部满足关键词命中闸门")
    return 0


if __name__ == "__main__":
    sys.exit(main())
