"""JVG v1.0 — Jev 禁区闸（Jev Misuse Gate）。

★ 命题：Jev 生态里所有工具都在解决「怎么用得更好」，
  没有一处把「哪里不该用」变成代码里的红灯。厂商不会做（等于劝退），
  社区工具都在做加法，于是**禁区只在文档里，不在 CI 里**。

★ 本件判据**全部可指源**，不是拍脑袋：
  · math        TypeSafe 官方文档自查：数数/精确算术/日期推算/多跳推理极差，禁用于金融结算。
  · chinese     以英文语料为主训练，中文细粒度分类准确率下滑（官方文档明示）。
  · irreversible 不可逆动作（支付/删除/权限）需极高阈值或人工；提示词注入风险仍在（官方文档 + 三方实测）。
  · coarse_unit 长段落整块问会把内容判成 other 且低置信（逐句问则判对）—— 实测，见 README。

★ 与第九件 DSD 的正交：DSD 读**已有判定日志**算校准/经济性（事后体检），
  JVG 在**调用之前**拦住不该迁移的调用点（事前准入）。输入不同、时点不同、问题不同。
"""
from __future__ import annotations

import json
import os
import re
import sys
from typing import Any

JVG_VERSION = "1.0"

# ---------------------------------------------------------------- 判据（模块级，verify.py 靠改写它们喂错数据）
MATH_RE = re.compile(
    r"\b(?:count|sum|total_amount|calculate|arithmetic|invoice|reconcil|"
    r"date_diff|datetime|timedelta|time_diff|账|对账|结算|金额|计数)\b",
    re.IGNORECASE)
CHINESE_RE = re.compile(r"[一-鿿]{2,}")
# ★ 中文任务词必须显式列进词表：把任务词只写英文（classif/categor…）时，
#   纯中文的判定任务会静默零命中（与 BRA「中文正则 \b 静默失效」同族的第二次形态）。
CHINESE_TASK_RE = re.compile(
    r"\b(?:classif|categor|label|judge|noul|choice|score|categoris)\w*|分类|归类|判断|评级|打标",
    re.IGNORECASE)
# ★ 词表必须容纳「运行时形态」而不是只在文档里见过的写法：
#   `subprocess.run(['rm', '-rf', x])` 的真实源码里 rm 后面接的是 `'` `,` `'`，
#   不是空白 —— 写成 `\brm\s+-rf\b` 时**永远匹配不到这种真实写法**，且不报错，静默零命中。
#   `rm[^\w\n]*-rf` 用「非单词非换行」吞掉引号/逗号/空格的任意组合，两种写法都吃。
IRREVERSIBLE_RE = re.compile(
    r"\brm[^\w\n]*-rf\b|\b(?:delete|refund|transfer|payment|charge|migrat|"
    r"drop\s+table|truncate|force\s+push|权限|退款|转账|删除|支付|授权)\b",
    re.IGNORECASE)
COARSE_RE = re.compile(
    r"\b(?:paragraph|whole\s+doc|full\s+page|document|长文本|整段|全文|raw_text|"
    r"page_text|article|response_text)\b", re.IGNORECASE)

# ★ CALL_SITE_RE 的前两版都太宽：
#   v1 用 `\bjev\b|typesafe` 这种「名词级」词条 ⇒ 1146 个文件里 931 个"含调用点"(81%)。
#   v2 用 `TYPESAFE_API_KEY|typesafe.ai|TypeSafeBackend` ⇒ 命中里**几乎全是假阳性**：
#     269 处 TYPESAFE_API_KEY 是配置键不是调用、29 处 typesafe.ai 是文档 URL、
#     13 处 TypeSafeBackend 是类定义/导入、还有注释掉的示例行、docstring 里的 URL。
#   v3 改成**动词级**，只认三种真调用形态（全部实测自 corpus）：
#     · client.system_one(     （blakestone-x/jev-mcp:140、PyModel/jev-judge-mcp:140）
#     · this.client.systemOne( （Mawfyy/jevflow:72、simota/tenbin:110）
#     · self._post("/v1/systemone", body)  ← 端点必须**带引号**，
#       把 "* Wire shapes mirror TypeSafe's /v1/systemone API" 这类块注释排除掉。
CALL_SITE_RE = re.compile(
    # ★ 用单引号串：这里要塞 " ' ` 三种引号，双引号串会被前一处 `"` 截断（第一次写就栽在这）。
    #   端点用**定宽后顾断言** `(?<=["\'`])` 要求 `/v1` 前面就是引号，避开变长 lookbehind。
    r'system_one\s*\(|systemOne\s*\(|(?<=["\'`])\s*/v1/systemone|'
    r'TypeSafeClassifier|TypesafeClassifier',
    re.IGNORECASE)
# 但 `def system_one(...)` 是**包装器定义**，不是一次调用 —— 那行只是转发，禁区特征归它不管。
CALL_DEF_RE = re.compile(
    r"(?:def|class|function)\s+\w*(?:system_one|systemOne)\s*\(", re.IGNORECASE)

# ★ 只在代码文件里判定。.md/.json 里提一次 "Jev" 不等于这里调了一次 API ——
#   把文档当代码扫出来的命中率毫无意义（见 scan_file 里的 SKIP_EXT）。
CODE_EXT = {".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs", ".go", ".rs", ".sh"}
SKIP_EXT = {".md", ".json", ".lock", ".yaml", ".yml", ".toml", ".txt"}

# 语料规模上报口径（§S3.5 第 5 条：口径先钉死再核）
SCAN_SCOPE = "仅代码文件（.py/.ts/.tsx/.js/.jsx/.mjs/.cjs/.go/.rs/.sh）；文档不参与判定"

# 位置：禁区特征必须与 Jev 调用处在**同一个上下文窗口**内（同函数/相邻若干行）。
# ★ 第一版只按文件聚合 ⇒ 文件里任何一处有 rm -rf 就把整个文件的 Jev 调用全判成违规；
#   位置不参与 ⇒ 又是另外一种「只改一半」。位置与内容必须同时成立。
CONTEXT_LINES = 12          # 调用点上下各取多少行算同一个上下文
IRREVERSIBLE_THRESHOLD = 1  # 上下文里出现几次不可逆操作词才算踩线
CHINESE_MIN = 8             # 上下文里至少几个 CJK 字符才算中文任务
COARSE_MIN = 1              # 粗粒度输入词至少命中几次

# fixture 期望表（verify.py 注入错数据用）
FIXTURE_EXPECT: dict[str, list[str]] = {
    # 只报 f01 真踩了一类，f02 干净 —— 期望集合写全，verify 会断言"没有多报也没有少报"
    "f01_math": ["math"],
    "f02_clean": [],
    "f03_chinese": ["chinese"],
    "f04_irreversible": ["irreversible"],
    "f05_coarse": ["coarse_unit"],
    "f06_multizone": ["math", "irreversible"],  # 多类并存，不许短路只报第一类
    "f07_context": [],                          # trap：rm -rf 在别的函数里，不算同一个上下文
    "f08_distant": [],
}
ZONES = ("math", "chinese", "irreversible", "coarse_unit")


def zones_of_ctx(lines: list[str], ci: int) -> list[str]:
    """返回该行**所有站得住**的禁区档，不是短路后的第一个。

    ★ 与 SAA 第 3 条踩坑同族：第一版写成「命中即 return」，
      多区并存的文件（f06）会被只报一类，而「一处踩两个禁区」本身才是结论。
      调顺序是治不好的（每调一次引入一次新取舍），所以全档列出。
    """
    lo, hi = max(0, ci - CONTEXT_LINES), min(len(lines), ci + CONTEXT_LINES + 1)
    ctx = "\n".join(lines[lo:hi])
    z: list[str] = []

    # ★ 位置必须参与：禁区特征要在**同一上下文**内。f07 的 rm -rf 在隔壁函数 ≠ 同一个调用点的问题。
    if MATH_RE.search(ctx):
        z.append("math")
    # 中文任务：上下文有足够中文，**并且**上下文里出现了任务词（分类/判断/classify…）。
    # ★ `self_line or ctx` 是错的（第一版就这么写的，f03 三条件全 True 却返回 []）：
    #   self_line 非空就会短路，调用行本身几乎不含任务词 ⇒ 中文判定任务必然漏报。
    #   ctx 已经包含 self_line，所以「搜 ctx」同时覆盖同行与邻近行，不需要 or 链。
    if CHINESE_MIN <= len(re.findall(r"[一-鿿]", ctx)) and CHINESE_TASK_RE.search(ctx):
        z.append("chinese")
    if len(re.findall(IRREVERSIBLE_RE, ctx)) >= IRREVERSIBLE_THRESHOLD:
        z.append("irreversible")
    if len(re.findall(COARSE_RE, ctx)) >= COARSE_MIN:
        z.append("coarse_unit")
    return z


def scan_file(path: str) -> dict:
    try:
        text = open(path, encoding="utf-8", errors="replace").read()
    except OSError:
        return {"rel": os.path.basename(path), "error": "unreadable", "call_sites": 0, "zones": {}}
    lines = text.splitlines()
    out = {"rel": os.path.basename(path), "call_sites": 0, "zones": {},
           "sites": [], "error": None}
    hits: dict[str, int] = {}
    for i, line in enumerate(lines):
        if CALL_DEF_RE.search(line):
            continue                      # 包装器定义行不算调用点
        if not CALL_SITE_RE.search(line):
            continue
        out["call_sites"] += 1
        z = zones_of_ctx(lines, i)
        for zz in z:
            hits[zz] = hits.get(zz, 0) + 1
        out["sites"].append({"line": i + 1, "zones": z})
    out["zones"] = hits
    return out


def batch(root: str) -> dict:
    results = []
    for dirpath, _dirs, files in os.walk(root):
        for fn in files:
            if fn == "_manifest.json" or fn.endswith(("_cli.py", "collect.py")):
                continue
            if fn.endswith(tuple(SKIP_EXT)) or not fn.endswith(tuple(CODE_EXT | SKIP_EXT)):
                continue
            results.append(scan_file(os.path.join(dirpath, fn)))
    ok = [r for r in results if not r.get("error")]
    # ★ 最大单档命中数必须常驻可见（§S3.5 第 4 条：报 0 分不清「没这现象」和「阈值挡住了」）
    peak = max([(r["zones"] and max(r["zones"].values())) or 0 for r in ok] or [0])
    # ★ 而且是**分档**的：只有全局峰值时，某个档报 0 会被别的档的峰值盖住。
    #   分档峰值全为 0 ⇒ 词表/判据没覆盖这一档（要修）；分档峰值非 0 ⇒ 是门槛在挡（调门槛）。
    zone_peaks = {z: max([r["zones"].get(z, 0) for r in ok] or [0]) for z in ZONES}
    n_site_files = sum(1 for r in ok if r["call_sites"] > 0)
    return {
        "n_files": len(results), "n_readable": len(ok),
        "n_with_sites": n_site_files, "peak_zone_hits": peak,
        "zone_peaks": zone_peaks,
        "tally": {z: sum(r["zones"].get(z, 0) for r in ok) for z in ZONES},
        "results": results,
    }


def main() -> None:
    raw = sys.argv[1:]
    as_json = "--json" in raw
    args = [a for a in raw if a != "--json"]
    if not args:
        print(__doc__)
        sys.exit(2)
    # ★ 连踩两次：第一次把子命令 "batch" 当成目录，第二次把开关本身删了导致 --json 分支永不触发。
    #   root 取**最后一个**位置参数；开关不可能是目录，子命令已在末尾位置之外。
    root = args[-1] if args[0] != "batch" else args[1]
    out = batch(root)
    if as_json:
        print(json.dumps(out, ensure_ascii=False))
        return
    t = out["tally"]
    print(f"扫描 {out['n_files']} 文件（可读 {out['n_readable']}）| 含 Jev 调用点的文件 {out['n_with_sites']}")
    print(f"禁区命中：{json.dumps(t, ensure_ascii=False)}")
    print(f"单文件最高命中档：{out['peak_zone_hits']}")
    if out["peak_zone_hits"] == 0 and out["n_with_sites"] > 0:
        print("  ⚠ 有调用点却零命中 —— 可能是判据太严也可能是词表漏了，必须先跑探针再下结论（§S3.5）")


if __name__ == "__main__":
    main()
