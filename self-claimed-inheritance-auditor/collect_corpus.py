#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CIA 语料采集器 —— 第二十四条「人和 AI 完全融合」

命题（待 Step 2.5 自攻）：
  AI 从经验里**自主创造 skill**（Hermes 官方语：creates skills from experience /
  Skills self-improve during use），于是"我学会了 X"成了可继承的自述。
  但「写下了」与「真获得了」之间没有任何对账。

★ 通道纪律沿用 SRA：全部走 urllib，不用 curl
  （curl 是 Windows 原生程序，不认 Git Bash 的 /c/Users/...，会静默建不出文件）
落盘闸门（任一条不过 ⇒ 非零退出，不许拿空语料往下走）：
  return 3: 全部为空（采空）
  return 4: 写出 0 字节文件
  return 5: 存在 0 字节文件
  return 6: 关键词闸门未过（CORE ≥HIT_MIN / SIDE ≥SIDE_MIN）
  return 7: CORE 源 <5
"""
from __future__ import annotations

import hashlib
import html as _html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent          # ★ 不能多 .parent
ART = ROOT / "_raw" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

MIN_BYTES = 1500
HIT_MIN = 2
SIDE_MIN = 1
TIMEOUT = 45

# 每条 (文件名, URL, 来源标注, 可信度, 角色)
#   CORE = 承载主题主张，进 ≥5 源计数
#   SIDE = 旁证（仅在时间线/场合上交叉），单独记账
#   REF  = 参考材料（用来核实某一具体事实），不设词闸
SOURCES: list[tuple[str, str, str, str, str]] = [
    ("corpus_hermes_readme.md",
     "https://raw.githubusercontent.com/NousResearch/hermes-agent/main/README.md",
     "一手·Nous Research 官方仓库 README（命题核心出处）", "极高", "CORE"),
    ("corpus_openclaw_readme.md",
     "https://raw.githubusercontent.com/openclaw/openclaw/main/README.md",
     "一手·OpenClaw 官方仓库 README", "极高", "CORE"),
    ("corpus_openclaw_site.md",
     "https://openclaw.ai/",
     "一手·OpenClaw 官网", "极高", "CORE"),
    ("corpus_arxiv_2607_24300.md",
     "https://arxiv.org/html/2607.24300v1",
     "一手·论文（自写验证不可靠 / verifier-deployment gap）", "极高", "CORE"),
    ("corpus_uniontech_aios.md",
     "https://www.uniontech.com/news-info/2917.html",
     "一手·统信软件官方（AIOS 官方口径）", "高", "CORE"),
    ("corpus_worldprogramming_cua.md",
     "https://www.worldprogramming.org/posts/how-do-computer-use-agents-work-klvyes",
     "二手·行业快报（Hermes 定义出处；作者自述任职 Factory）", "中", "CORE"),
    ("corpus_hermes_docs_skills.md",
     "https://hermes-agent.nousresearch.com/docs/user-guide/features/skills",
     "一手·Hermes 官方能力文档（skill 创建）", "极高", "REF"),
]

# 通道探测（RA-5：通道失败与内容缺失必须分开记账）
PROBES: list[tuple[str, str]] = [
    ("clawhub_registry", "https://clawhub.ai"),
    ("agentskills_standard", "https://agentskills.io"),
]

# 关键词闸门：本主题的工程词，缺 HIT_MIN 个 ⇒ 视为采到别的页面了
KEYWORDS = ["skill", "self-improv", "autonomous", "memory", "verifier",
            "deploy", "SKILL.md", "技能", "自改进", "自我改进", "记忆", "自主"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _read(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(
        url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        final = r.geturl()
    return raw, final


def _strip_html(h: str) -> str:
    h = re.sub(r"(?is)<(script|style|svg|nav|footer)\b.*?</\1>", " ", h)
    h = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>|</tr>", "\n", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    h = _html.unescape(h)
    h = re.sub(r"[ \t\xa0]+", " ", h)
    h = re.sub(r"\n{3,}", "\n\n", h)
    return h.strip()


def _kw_hits(text: str) -> list[str]:
    low = text.lower()
    return [k for k in KEYWORDS if k.lower() in low]


def main() -> int:
    manifest: dict[str, Any] = {
        "topic": "自述继承 / Self-Claimed Inheritance（AI 自主写 skill 的能力对账）",
        "collected_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "sources": [],
        "probes": [],
        "keyword_gate": {"keywords": KEYWORDS, "hit_min": HIT_MIN},
    }

    for name, url, grade, trust, role in SOURCES:
        try:
            raw, final = _read(url)
        except Exception as e:                       # 通道失败要记账，不许静默跳过
            print("  [通道失败] %s <- %s : %s" % (name, url, type(e).__name__))
            manifest["sources"].append({"file": name, "url": url, "grade": grade,
                                        "trust": trust, "role": role,
                                        "status": "CHANNEL_FAIL",
                                        "error": "%s: %s" % (type(e).__name__, e)})
            continue
        text = raw.decode("utf-8", errors="replace")
        if "<html" in text[:4000].lower():
            text = _strip_html(text)
        text = text.strip()
        (ART / name).write_text(text, encoding="utf-8")   # ★ 绝对路径 Path，绕过 curl 坑
        hits = _kw_hits(text)
        density = len(hits) / len(KEYWORDS)
        rec = {"file": name, "url": url, "final_url": final, "grade": grade,
               "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
               "trust": trust, "role": role, "status": "OK",
               "bytes": len(text.encode("utf-8")), "chars": len(text),
               "keyword_hits": hits, "n_keywords": len(hits),
               "density": round(density, 3)}
        manifest["sources"].append(rec)
        print("  [%s] %-32s %7d B  kw=%d/%d density=%.2f role=%s"
              % (rec["status"], name, rec["bytes"], len(hits), len(KEYWORDS),
                 density, role))

    for pname, purl in PROBES:
        try:
            raw, _ = _read(purl)
            rec = {"probe": pname, "url": purl, "status": "OK", "bytes": len(raw)}
        except Exception as e:
            rec = {"probe": pname, "url": purl, "status": "CHANNEL_FAIL",
                   "error": "%s: %s" % (type(e).__name__, e)}
        manifest["probes"].append(rec)
        print("  [探针] %-18s %s" % (pname, rec["status"]))

    # ── 落盘闸门 ────────────────────────────────────────────────
    files = sorted(ART.glob("*.md"))
    zero = [f for f in files if f.stat().st_size == 0]
    print("\n[闸门] 落盘 %d 个 .md，其中 0 字节 %d 个" % (len(files), len(zero)))
    if len(files) == 0 or len(zero) == len(files):
        print("[闸门] 失败 3：全部为空 ⇒ 采空，不许往下走")
        return 3
    if zero:
        print("[闸门] 失败 5：存在 0 字节文件 %s" % [f.name for f in zero])
        return 5

    # 三级角色，各有各的闸
    for rec in manifest["sources"]:
        if rec.get("status") != "OK" or rec["role"] == "REF":
            continue
        need = HIT_MIN if rec["role"] == "CORE" else SIDE_MIN
        if rec["n_keywords"] < need:
            print("[闸门] 失败 6：%s 仅命中 %d 个关键词（CORE 需 >=%d / SIDE 需 >=%d）"
                  % (rec["file"], rec["n_keywords"], HIT_MIN, SIDE_MIN))
            return 6

    # 低密度告警：角色由我事先声明，不由密度自动判定（启发式越权，SRA 已踩过）
    WARN_DENSITY = 0.35
    low_density = []
    for rec in manifest["sources"]:
        if rec.get("status") == "OK" and rec.get("density", 1.0) < WARN_DENSITY:
            low_density.append((rec["file"], rec["density"]))
    for f, d in low_density:
        print("  [告警] %-32s density=%.2f < %.2f ⇒ 引用它之前先确认它真支撑该主张"
              % (f, d, WARN_DENSITY))

    # ── 去重闸：同一份内容算两个源 = 把一个来源冒领成两个 ──
    seen: dict[str, str] = {}
    dups: list[tuple[str, str, str]] = []
    for rec in manifest["sources"]:
        if rec.get("status") != "OK":
            continue
        fp = hashlib.sha256(rec["text_sha256"].encode()).hexdigest()[:16]
        rec["sha16"] = fp
        if fp in seen:
            dups.append((rec["file"], seen[fp], rec["url"]))
            rec["role"] = "DUP"
            rec["dup_of"] = seen[fp]
        else:
            seen[fp] = rec["file"]
    for f, of, u in dups:
        print("  [去重] %-32s 与 %s 内容相同 ⇒ role 置 DUP（不进源计数）" % (f, of))

    manifest["coverage"] = {
        "total_sources": len(SOURCES),
        "ok": len([r for r in manifest["sources"] if r.get("status") == "OK"]),
        "channel_fail": len([r for r in manifest["sources"]
                             if r.get("status") == "CHANNEL_FAIL"]),
        "core": len([r for r in manifest["sources"]
                     if r.get("status") == "OK" and r.get("role") == "CORE"]),
        "side": len([r for r in manifest["sources"]
                     if r.get("status") == "OK" and r.get("role") == "SIDE"]),
        "dup": len([r for r in manifest["sources"] if r.get("role") == "DUP"]),
        "low_density": low_density,
        "duplicates": [{"file": f, "dup_of": of, "url": u} for f, of, u in dups],
    }
    (ART / "_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    cov = manifest["coverage"]
    print("[闸门] 关键词闸门全过（OK %d/%d，通道失败 %d）"
          % (cov["ok"], cov["total_sources"], cov["channel_fail"]))
    print("[闸门] 主题源 CORE=%d / 旁证 SIDE=%d / 重复 DUP=%d"
          % (cov["core"], cov["side"], cov["dup"]))
    if cov["core"] < 5:
        print("[闸门] 失败 7：CORE 源仅 %d 个（<5）⇒ 不够 Step 2 门槛，须补源" % cov["core"])
        return 7
    print("[采集] 完成 → %s" % ART)
    return 0


if __name__ == "__main__":
    sys.exit(main())
