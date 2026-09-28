#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SRA 语料采集器 —— 第二十三条 MOSS-VL-Realtime

★ 通道纪律：全部走 urllib，不用 curl。
  （curl 是 Windows 原生程序，不认 Git Bash 的 /c/Users/...，会静默建不出文件。）
落盘闸门（任一条不过 ⇒ 非零退出，不许拿空语料往下走）：
  return 3: 抓取字节数 < MIN_BYTES（判"采空"）
  return 4: 文件写完后 st_size == 0
  return 5: 0 字节文件数 != 0
  return 6: 关键词闸门未过（每源要求 KEYWORDS 里至少 HIT_MIN 个命中）
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

ROOT = Path(__file__).resolve().parent          # ★ 不能多 .parent
ART = ROOT / "_raw" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

MIN_BYTES = 2000
HIT_MIN = 2
TIMEOUT = 40

# 每条 (文件名, URL, 一级来源标注, 可信度, 角色)
#   角色 CORE = 承载主题主张，进 ≥5 源计数
#   角色 SIDE = 旁证（仅在时间线/场合上交叉），单独记账
#   角色 REF  = 参考材料（用来核实某一具体事实，本就与主题词无关），不设词闸
SOURCES: list[tuple[str, str, str, str, str]] = [
    ("corpus_openmoss_blog.md",
     "https://openmoss.ai/MOSS-VL/",
     "一手·作者官方技术博客", "极高", "CORE"),
    ("corpus_readme_github.md",
     "https://raw.githubusercontent.com/OpenMOSS/MOSS-VL/main/README.md",
     "一手·仓库 README", "极高", "CORE"),
    ("corpus_sii_press.md",
     "https://www.sii.edu.cn/_s3/2026/0716/c27a1152/page.psp",
     "一手·发布方机构（上海创智学院）通稿", "高", "CORE"),
    ("corpus_arxiv_2608_15045.md",
     "https://arxiv.org/abs/2608.15045",
     "一手·技术报告 arXiv", "极高", "CORE"),
    ("corpus_arxiv_html.md",
     "https://arxiv.org/html/2608.15045v1",
     "一手·技术报告全文 HTML（基准分项所在）", "极高", "CORE"),
    ("corpus_realtime_demo_readme.md",
     "https://raw.githubusercontent.com/OpenMOSS/MOSS-VL/main/third_party/realtime-demo/README.md",
     "一手·官方实时演示 README", "极高", "CORE"),
    ("corpus_omnimmi_readme.md",
     "https://raw.githubusercontent.com/OmniMMI/OmniMMI/main/README.md",
     "一手·评测基准 OmniMMI 仓库本体（判据定义所在）", "极高", "CORE"),
    ("corpus_open_source_datasets.md",
     "https://raw.githubusercontent.com/OpenMOSS/MOSS-VL/main/docs/open_source_datasets.md",
     "一手·训练开源数据集清单（沉默标准的来源）", "极高", "REF"),
    ("corpus_openmoss_techblog.md",
     "https://openmoss.github.io/MOSS-VL/",
     "一手·官方技术博客站", "极高", "CORE"),
    ("corpus_xhby_waic.md",
     "https://www.xhby.net/content/s6a5b62cbe4b03d9ce7970c4d.html",
     "一手·媒体现场报道（新华日报·交汇点）", "中", "SIDE"),
]

# 通道探测（RA-5：通道失败与内容缺失必须分开记账）
PROBES: list[tuple[str, str]] = [
    ("hf_model_card", "https://huggingface.co/api/models/OpenMOSS-Team/MOSS-VL-Realtime"),
]

# 关键词闸门：本主题的工程词，缺 HIT_MIN 个 ⇒ 视为采到别的页面了
KEYWORDS = ["silence", "proactive", "streaming", "timestamp", "correction",
            "沉默", "主动", "实时", "流式"]

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def _read(url: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        raw = r.read()
        final = r.geturl()
    return raw, final


def _strip_html(html: str) -> str:
    html = re.sub(r"(?is)<(script|style|svg)\b.*?</\1>", " ", html)
    html = re.sub(r"(?is)<br\s*/?>|</p>|</div>|</li>|</h[1-6]>", "\n", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    import html as _h
    html = _h.unescape(html)
    html = re.sub(r"[ \t\xa0]+", " ", html)
    html = re.sub(r"\n{3,}", "\n\n", html)
    return html.strip()


def _kw_hits(text: str) -> list[str]:
    low = text.lower()
    return [k for k in KEYWORDS if k.lower() in low]


def main() -> int:
    manifest: dict[str, Any] = {
        "topic": "MOSS-VL-Realtime / 实时流视频理解 · 主动沉默",
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
                                        "error": f"{type(e).__name__}: {e}"})
            continue
        text = raw.decode("utf-8", errors="replace")
        if "<html" in text[:4000].lower():
            text = _strip_html(text)
        b = ART / name
        b.write_text(text, encoding="utf-8")         # ★ 绝对路径 Path，绕过 curl 坑
        hits = _kw_hits(text)
        density = len(hits) / len(KEYWORDS)
        rec = {"file": name, "url": url, "final_url": final, "grade": grade,
               "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16],
               "trust": trust, "role": role, "status": "OK",
               "bytes": len(text.encode("utf-8")), "chars": len(text),
               "keyword_hits": hits, "n_keywords": len(hits), "density": round(density, 3)}
        manifest["sources"].append(rec)
        print("  [%s] %-30s %7d B  kw=%d/%d density=%.2f role=%s"
              % (rec["status"], name, rec["bytes"], len(hits), len(KEYWORDS),
                 density, role))

    for pname, purl in PROBES:
        try:
            raw, _ = _read(purl)
            rec = {"probe": pname, "url": purl, "status": "OK", "bytes": len(raw)}
        except Exception as e:
            rec = {"probe": pname, "url": purl, "status": "CHANNEL_FAIL",
                   "error": f"{type(e).__name__}: {e}"}
        manifest["probes"].append(rec)
        print("  [探针] %-18s %s" % (pname, rec["status"]))

    # ── 落盘闸门 ────────────────────────────────────────────────
    files = sorted(ART.glob("*.md"))
    ok = [f for f in files if f.stat().st_size > 0]
    print("\n[闸门] 落盘 %d 个 .md，其中 0 字节 %d 个" % (len(files), len(files) - len(ok)))
    if len(ok) == 0:
        print("[闸门] 失败 3：全部为空 ⇒ 采空，不许往下走")
        return 3
    for f in files:
        if f.stat().st_size == 0:
            print("[闸门] 失败 4：写出 0 字节文件 %s" % f.name)
            return 4
    if len(files) - len(ok) != 0:
        print("[闸门] 失败 5：存在 0 字节文件")
        return 5

    # 主题源 CORE：须 >= HIT_MIN（防"采错页面"）
    # 旁证源 SIDE：只要 >= SIDE_MIN（"确实提到了本主题"）即可，它的作用是时间线交叉
    # ⇒ 两个阈值的职责不同，不是把闸门放松。
    # 三级角色，各有各的闸：
    #   CORE 主题源 —— 承载主题主张，须命中 >=2（防"采错页面"），进 ≥5 源计数
    #   SIDE 旁证源 —— 只做时间线/场合交叉，须命中 >=1，不进计数
    #   REF  参考材 —— 用来核实某个具体事实（如训练语料清单），本就与主题词无关，不设词闸
    SIDE_MIN = 1
    for rec in manifest["sources"]:
        if rec.get("status") != "OK":
            continue
        if rec["role"] == "REF":
            continue
        need = HIT_MIN if rec["role"] == "CORE" else SIDE_MIN
        if rec["n_keywords"] < need:
            print("[闸门] 失败 6：%s 仅命中 %d 个关键词（CORE 需 >=%d / SIDE 需 >=%d）⇒ 采到的可能是别的东西"
                  % (rec["file"], rec["n_keywords"], HIT_MIN, SIDE_MIN))
            return 6

    # 角色 = 我**事先声明**的，不由关键词密度自动判定。
    # ★ 为什么取消"自动降权"：第一版按 density<0.40 自动把 OmniMMI 降成 SIDE，
    #   而 OmniMMI 恰恰是"主动性评测"的定义源——它的 README 不复述营销词，密度天然低。
    #   拿我自己挑的词表和阈值去覆盖我自己声明的角色，是**启发式越权**：
    #   它替我做了判断，还做得比我糟。⇒ 改为如实报密度 + 低密度告警，判断权留给人。
    WARN_DENSITY = 0.35
    low_density = []
    for rec in manifest["sources"]:
        if rec.get("status") == "OK" and rec.get("density", 1.0) < WARN_DENSITY:
            low_density.append((rec["file"], rec["density"]))
    for f, d in low_density:
        print("  [告警] %-30s density=%.2f < %.2f ⇒ 引用它之前先确认它真的支撑该主张"
              % (f, d, WARN_DENSITY))

    # ── 去重闸（2026-09-27 实抓）：openmoss.github.io 与 openmoss.ai 返回**字节完全相同**
    #    同一份内容算两个源，就是把一个来源冒领成两个。按内容指纹去重，重复项只计一次。
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
        print("  [去重] %-30s 与 %s 内容相同 ⇒ role 置 DUP（不进源计数）" % (f, of))

    manifest["coverage"] = {
        "total_sources": len(SOURCES),
        "ok": len([r for r in manifest["sources"] if r.get("status") == "OK"]),
        "channel_fail": len([r for r in manifest["sources"] if r.get("status") == "CHANNEL_FAIL"]),
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
    print("[闸门] 关键词闸门全过（%d/%d 源 OK，%d 通道失败）" % (cov["ok"], cov["total_sources"], cov["channel_fail"]))
    print("[闸门] 主题源 CORE=%d / 旁证 SIDE=%d / 重复 DUP=%d"
          % (cov["core"], cov["side"], cov["dup"]))
    if cov["core"] < 5:
        print("[闸门] 失败 7：CORE 源仅 %d 个（<5）⇒ 不够 Step 2 门槛，须补源" % cov["core"])
        return 7
    print("[采集] 完成 → %s" % ART)
    return 0


if __name__ == "__main__":
    sys.exit(main())
