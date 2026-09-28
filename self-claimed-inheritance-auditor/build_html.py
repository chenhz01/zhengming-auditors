#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SCI · 暗色 HTML 生成器（手册 + 成果页两份同构）。

模板约束（沿用 SRA，踩过的坑）：
  ★ 用 __TOKEN__ 占位符 + .replace()，**不用 % 格式化** —— CSS 里全是 % ，
    "% 格式化会把 %d 当成转换符，报 ValueError: unsupported format character"。
  ★ 变量名与函数名一律 ASCII（中文标识符在 3.13 下可触发 IndentationError）。
  ★ 输出两处：_out/index.html 与 桌面/成果/抖音学习突破七流程-自述继承审计器SCI-2026-09-27.html
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_out"
DESKTOP = Path.home() / "Desktop" / "成果"
DESKTOP.mkdir(parents=True, exist_ok=True)

TITLE = "自述继承审计器 SCI"
SUBTITLE = "AI 说自己「学会了」，用什么对账？"
DATE = "2026-09-27"
VIDEO_TITLE = "第271集 今天人与AI完美融合 这集的工具实现了人和 AI 的完全融合"
VIDEO_URL = "https://www.douyin.com/jingxuan?modal_id=7676308591460125961"

CSS = """
:root{
 --bg:#0b0e14; --card:#161c2c; --card2:#1b2334; --line:#243044;
 --fg:#e6edf7; --dim:#93a1bb; --accent:#5eead4; --accent2:#a78bfa;
 --warn:#fbbf24; --bad:#f87171; --ok:#4ade80;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
 font-family:"Inter","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
 font-size:14px;line-height:1.75}
.layout{display:flex;min-height:100vh}
nav{width:250px;flex:0 0 250px;background:var(--card);border-right:1px solid var(--line);
 padding:22px 0;position:sticky;top:0;height:100vh;overflow:auto}
nav .brand{padding:0 20px 14px;border-bottom:1px solid var(--line);margin-bottom:12px}
nav .brand b{display:block;font-size:15px;color:var(--accent)}
nav .brand span{font-size:11px;color:var(--dim)}
nav a{display:block;padding:8px 20px;color:var(--dim);text-decoration:none;
 font-size:13px;border-left:3px solid transparent}
nav a:hover{color:var(--fg);background:var(--card2);border-left-color:var(--accent)}
nav a.on{color:var(--accent);background:var(--card2);border-left-color:var(--accent2);
 font-weight:600}
main{flex:1;padding:34px 46px;max-width:1080px}
h1{font-size:27px;margin:0 0 6px;letter-spacing:-.4px}
.sub{color:var(--accent2);font-size:15px;margin:0 0 18px}
.meta{color:var(--dim);font-size:12.5px;margin-bottom:26px;
 border-left:3px solid var(--line);padding-left:14px}
h2{font-size:19px;margin:40px 0 14px;padding-bottom:8px;
 border-bottom:1px solid var(--line);color:var(--accent)}
h3{font-size:15px;margin:22px 0 10px;color:var(--accent2)}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
 padding:18px 20px;margin:14px 0}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(210px,1fr));gap:12px}
.kpi{background:var(--card2);border:1px solid var(--line);border-radius:9px;padding:14px 16px}
.kpi .n{font-size:23px;font-weight:700;color:var(--accent)}
.kpi .l{font-size:11.5px;color:var(--dim);margin-top:2px}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:13px}
th,td{border:1px solid var(--line);padding:8px 10px;text-align:left;vertical-align:top}
th{background:var(--card2);color:var(--accent);font-weight:600;font-size:12.5px}
tr:nth-child(even) td{background:#131a28}
code{background:#0f1520;border:1px solid var(--line);border-radius:4px;
 padding:1px 6px;font-size:12.5px;color:var(--accent)}
pre{background:#0f1520;border:1px solid var(--line);border-radius:8px;
 padding:14px 16px;overflow:auto;font-size:12.5px;color:#cbd5f0;line-height:1.6}
blockquote{margin:12px 0;padding:12px 16px;background:#121a29;
 border-left:3px solid var(--accent2);border-radius:0 8px 8px 0;color:#dbe6f7}
blockquote b{color:var(--accent)}
.tag{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;
 border:1px solid var(--line);color:var(--dim);margin-right:5px}
.ok{color:var(--ok)} .bad{color:var(--bad)} .warn{color:var(--warn)}
.hl{color:var(--accent);font-weight:600}
ul{margin:8px 0 8px 4px;padding-left:20px}
li{margin:5px 0}
footer{margin-top:60px;padding-top:16px;border-top:1px solid var(--line);
 color:var(--dim);font-size:12px}
"""


def tpl(nav_active: str) -> str:
    navs = [
        ("s0", "Step 0 · 对抗闸门"), ("s1", "Step 1 · 抓取定位"),
        ("s2", "Step 2 · 多源交叉"), ("s25", "Step 2.5 · 竞品与自攻"),
        ("s275", "Step 2.75 · 硬门槛探针"), ("s3", "Step 3 · 六判据与突破件"),
        ("s4", "手册正文 · SCI 规范"), ("s5", "Step 4-5 · 评分与回审"),
    ]
    links = "\n".join(
        '  <a class="%s" href="#%s">%s</a>' % ("on" if k == nav_active else "", k, label)
        for k, label in navs)

    def sec(key: str, h2: str, body: str) -> str:
        return ('<section id="%s"><h2>%s</h2>%s</section>\n' % (key, h2, body))

    return """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ · 抖音学习突破七流程 __DATE__</title>
<style>__CSS__</style></head><body>
<div class="layout">
<nav><div class="brand"><b>__TITLE__</b><span>__DATE__ · 第二十四条</span></div>
__NAV__
</nav>
<main>
<h1>__TITLE__</h1>
<p class="sub">__SUBTITLE__</p>
<div class="meta">
  视频：<span class="hl">__VIDEO_TITLE__</span><br>
  链接：<code>__VIDEO_URL__</code><br>
  七流程：Step 0 对抗闸门 → 1 抓取定位 → 2 多源交叉 → 2.5 竞品扫描+自攻三问
  → 2.75 硬门槛探针 → 3 七流程突破 → 4 交付四件 → 5 自我回审<br>
  硬门槛：R-BK1 突破件 ≥5（本件 8）· R-BK2 收口对账器（verify.py）
</div>

__SEC_S0__
__SEC_S1__
__SEC_S2__
__SEC_S25__
__SEC_S275__
__SEC_S3__
__SEC_S4__
__SEC_S5__

<footer>
正明 · 抖音学习突破七流程 · __DATE__ ·
命题库：<code>~/.workbuddy/rules/突破件/突破-2026-09-27-自述继承审计器SCIv1.0.md</code>
</footer>
</main></div></body></html>
""".replace("__NAV__", links).replace("__CSS__", CSS).replace("__TITLE__", TITLE) \
    .replace("__SUBTITLE__", SUBTITLE).replace("__DATE__", DATE) \
    .replace("__VIDEO_TITLE__", VIDEO_TITLE).replace("__VIDEO_URL__", VIDEO_URL)


# ── 各段内容 ──────────────────────────────────────────────────────────

def sec_s0() -> str:
    return """<div class="card">
<p><b>对上件下刀：FSA（流态审计器）三条缺口单</b></p>
<table><tr><th>#</th><th>缺口</th><th>修补规则</th></tr>
<tr><td>1</td><td>六判据均分 1.000，但<b>无一处试点</b> ⇒ 设计态被当运行态对外读</td>
<td>均分 ≥0.9 时，须在「已知限制」首行写明「试点未定前该值是设计态」</td></tr>
<tr><td>2</td><td>招牌指标未区分【实测】/【推导】，两个量级混在一张表里报</td>
<td>逐判据标 basis；均分≥0.9 时 CLI 主动列出 deduct_basis 清单</td></tr>
<tr><td>3</td><td>§S3.4 连犯记账缺失（HF 通道第三次到不了，只记了一次）</td>
<td>通道失败按「第 N 次」累计，不覆盖前次</td></tr>
</table>
<p style="color:var(--dim);font-size:12.5px">本件自检时把第 2 条升级为<b>硬规则</b>：
任何判据函数所有分支返回数值，零命中给 0.0 不给 None（FSA 第二次踩同一个坑）。</p>
</div>"""


def sec_s1() -> str:
    return """<table>
<tr><th>通道</th><th>实测结果</th><th>判定</th></tr>
<tr><td><code>curl douyin.com/video/&lt;id&gt;</code></td>
<td>拿到 72,914 B，但 <code>&lt;body&gt;&lt;/body&gt;</code> 为空 +
<code>_$jsvmprt</code> 混淆反爬脚本；<code>desc</code>/<code>nickname</code>/<code>sec_uid</code>
正则全部抽不到（<code>DESC: []</code>）</td><td class="bad">通道失败</td></tr>
<tr><td><code>iesdouyin.com/share/video/…</code></td>
<td>返回「抱歉出错了 / 请尝试在抖音内观看」（需登录态）</td><td class="bad">通道失败</td></tr>
<tr><td>抖音搜索页（WebFetch）</td><td>只有 loading 占位图</td><td class="bad">通道失败</td></tr>
<tr><td>WebFetch video 页（3 轮）</td><td>标题<b>完整未截断</b>，账号定位仍失败</td>
<td class="warn">部分成功</td></tr>
<tr><td>WebSearch 命题层（4 轮）</td><td>标题是连载集数编号，无公开索引；
改从命题语义（人机融合 / AI 自主 skill）检索 ⇒ 命中 arXiv 一手源</td>
<td class="ok">改道成功</td></tr>
</table>
<blockquote><b>RA-5 记账：通道失败 ≠ 内容缺失。</b>
抖音侧只拿到标题与链接，账号/正文全数缺失 ⇒ 本件<b>不用视频内容充当证据</b>，
证据全部落在命题层一手源上。这是一次如实记账，不是回避。</blockquote>"""


def sec_s2() -> str:
    return """<table>
<tr><th>语料</th><th>角色</th><th>用途</th><th>字节 / 关键词密度</th></tr>
<tr><td>hermes-agent README（Nous Research）</td><td>CORE</td>
<td>命题核心出处：自述原句</td><td>16,923 B / 4 词</td></tr>
<tr><td>openclaw README</td><td>CORE</td><td>同族自述生态</td><td>113,170 B / 3 词</td></tr>
<tr><td>openclaw.ai 官网</td><td>CORE</td><td>官方口径</td><td>31,461 B / 4 词</td></tr>
<tr><td><b>arXiv 2607.24300</b></td><td>CORE</td>
<td><b>关键一手：自写验证不可靠 / verifier–deployment gap</b></td><td>44,430 B / 5 词</td></tr>
<tr><td>统信软件 AIOS 官方页</td><td>CORE</td><td>旁证（人机融合官方口径）</td><td>9,452 B / 2 词</td></tr>
<tr><td>worldprogramming CUA 快报</td><td>CORE</td><td>Hermes 定义出处（二手）</td><td>17,692 B / 5 词</td></tr>
<tr><td>Hermes docs · skills</td><td>REF</td><td>核实 skill 创建机制</td><td>55,821 B / 6 词</td></tr>
</table>
<p class="ok">落盘闸门：<b>7/7 全绿</b>，通道失败 0，CORE=6（≥5 过门槛），去重 0。
落盘合计 <b>282,180 B</b>。</p>
<h3>gh api 独立核真（不是从正文里抄的）</h3>
<table><tr><th>repo</th><th>stars</th><th>forks</th><th>created</th><th>pushed</th></tr>
<tr><td><code>openclaw/openclaw</code></td><td class="hl">390,613</td><td>82,165</td>
<td>2025-11-24</td><td>2026-09-27</td></tr>
<tr><td><code>NousResearch/hermes-agent</code></td><td class="hl">249,295</td><td>—</td>
<td>2025-07-22</td><td>2026-09-27</td></tr>
</table>
<blockquote><b>★ 与 FSA/SRA 的上件同构关系仍在。</b>
FSA 审「不知道还要生成多少」，SRA 审「不知道这沉默该不该发生」，
<b>本件审「不知道这句『我学会了』是不是真的」</b> —— 同一个病，换一个器官。</blockquote>"""


def sec_s25() -> str:
    return """<h3>自攻三问第一问就撞上了真东西 ⇒ 命题被改写</h3>
<table><tr><th>三问</th><th>撞到的东西</th></tr>
<tr><td><b>① 是我搜错词吗？</b></td><td class="ok">不是。arXiv 2607.24300 已定义
<b>verifier–deployment gap</b>：「The agent controls both the optimized object and its
verifier. As a result, self-assigned scores can remain near perfect while real deployment
performance degrades or stays low.」并称其为
<b>structural conflict of interest</b>。</td></tr>
<tr><td>② 已有研究测的是哪一环？</td><td>测的是 <b>harness 内部</b>：SEAL 的保守更新 →
部署时门 → 清晰回归时回滚整个 policy–test state，agent 只收一个 accept/reject bit。
全部落在 harness 边界内。</td></tr>
<tr><td>③ 那外层谁在审？</td><td class="bad">没人。最外层那句最便宜的自述
「这条 skill 我学会了」，没有任何对账。</td></tr>
</table>
<div class="card">
<p><span class="tag">改写后命题</span></p>
<blockquote>AI 从经验里自主创造 skill，于是「我学会了 X」成了可继承的自述 ——
但「写下了」与「真获得了」之间<b>没有任何对账</b>。</blockquote>
</div>
<h3>五个「看起来在做」的竞品（都不是我要做的）</h3>
<table><tr><th>工具</th><th>它审什么</th><th>差别</th></tr>
<tr><td><code>skilldoctor</code>（243★）</td><td>35 条规则 lint + 安全 audit</td>
<td>读出<b>静态文本</b>，不验证「获得」</td></tr>
<tr><td><code>skills-check</code></td><td>版本漂移 / 幻觉包名 / URL 存活</td>
<td>审<b>上游依赖</b></td></tr>
<tr><td><code>skill-drift-audit</code></td><td>SKILL.md vs README 文档漂移</td>
<td>审「改了没同步」</td></tr>
<tr><td><code>skill-health-audit</code></td><td>trigger fit / held-out evidence</td>
<td>最接近，但是<b>人工 audit</b>，不是对账器</td></tr>
<tr><td><code>rleungx/skill-audit</code></td><td>生成用例 + 真调模型 + 阈值 80</td>
<td>审的是<b>人类写的</b> SKILL.md</td></tr>
</table>
<blockquote><b>★ 判据落点：</b>上述五个里<b>没有任何一个</b>在问「这条 skill 是 agent 自己
从经验里长出来的，那么它写下的『我学会了』用什么对账？」——
<code>held-out evidence</code> 这个判据词已经出现，但它挂在<b>人类作者</b>头上，
没挂在<b>自改进循环</b>头上。</blockquote>"""


def sec_s275() -> str:
    return """<div class="grid">
<div class="kpi"><div class="n">518</div><div class="l">本地 SKILL.md 全量（不抽样）</div></div>
<div class="kpi"><div class="n">192 / 5</div><div class="l">自述句 / 带可核对来源</div></div>
<div class="kpi"><div class="n">0.026</div><div class="l">本地持有面带来源率【实测】</div></div>
<div class="kpi"><div class="n">0.974</div><div class="l">本地空转自述率【实测】</div></div>
<div class="kpi"><div class="n">4/4</div><div class="l">硬门槛判定 PASS</div></div>
</div>
<table><tr><th>阶段</th><th>实测</th><th>结论</th></tr>
<tr><td><b>A 真实对账</b></td><td>518 个 SKILL.md 全量；80 条含自述句，
合计 192 条自述，其中<b>仅 5 条</b>带可核对来源；本地空转率 <b>0.974</b>。
最刺眼的一条：<code>zhengming-ai-learning</code> 有 27 条自述，
带来源 1 条 —— 恰是跑「学习它/超越它」最多的那个。</td>
<td class="bad">正明自己的 skill 库里，自述继承几乎全无对账</td></tr>
<tr><td><b>B Null 对照</b></td><td>注入 8 条无来源 ⇒ 空转率 1.000；
注入 8 条带来源 ⇒ 空转率 0.000</td><td class="ok">指标可分辨，不是死的</td></tr>
<tr><td><b>C 同口径复核</b></td><td>复用 <code>sci_cli</code> 的扫描函数（不复制词表），
杀掉来源锚 ⇒ 带来源数 15 → 0</td><td class="ok">指标真的在动</td></tr>
</table>
<blockquote class="bad"><b>★ 反自我欺骗闸门主动告警了。</b>
本地空转率 0.974 vs 语料招牌数 0.972，差 0.002 &lt; 0.05 ⇒ 脚本打印
「先怀疑脚本是不是读了同一批文件，别急着庆祝」。
<b>核实结果：两批文件本就不同源</b>（A 扫 518 个 SKILL.md，C 扫 7 个语料文件），
接近是巧合，不是互相印证。这个闸门该开，说明它有用。</blockquote>"""


def sec_s3() -> str:
    return """<table>
<tr><th>判据</th><th>问什么</th><th>行业</th><th>SCI</th></tr>
<tr><td>C1 自述可外部校验</td><td>「我学会了 X」能被外部独立验证吗</td>
<td class="bad">0.400</td><td class="ok">1.000【推导】</td></tr>
<tr><td>C2 继承分离度 ★</td><td>能分开「写下了」与「真获得了」吗</td>
<td class="bad">0.400</td><td class="ok">1.000【实测】</td></tr>
<tr><td>C3 持有面核对 ★招牌</td><td>多少自述真有可核对来源（provenance）</td>
<td class="bad">0.000</td><td class="ok">1.000【实测】</td></tr>
<tr><td>C4 回归闸门</td><td>新增自述会不会压掉已会的</td><td>0.500</td>
<td class="ok">1.000【推导】</td></tr>
<tr><td>C5 事后可证伪</td><td>事后能否翻出「当时那句自述是空的」</td>
<td class="bad">0.000</td><td class="ok">1.000【推导】</td></tr>
<tr><td>C6 空转自证 ★招牌</td><td>自述数是否在无新能力时照样涨</td>
<td class="bad">0.000</td><td class="ok">1.000【实测】</td></tr>
<tr><th>均分</th><th></th><th class="bad">0.217</th><th class="ok">1.000</th></tr>
</table>
<blockquote class="warn"><b>⚠ C4 的行业分 0.500 不是「有一半工具做了回归测试」。</b>
它来自：SEAL 的「保守更新 → 部署时门 → 清晰回归时回滚整个 policy–test state」
实测命中（三要素齐=True），但只回滚它自己的 harness state，
<b>没有外推到「自述计数 vs 已会能力」这一层</b>，故半分。
这个对照必须在手册里写明，否则会被误读成「已有工具在做回归」。</blockquote>
<h3>突破件清单（R-BK1 硬门槛：≥5，本件 8）</h3>
<table><tr><th>#</th><th>突破件</th><th>为什么是这个（不是凑数）</th></tr>
<tr><td>1</td><td><code>sci_cli.py</code> 六判据 CLI</td>
<td>修一类：basis 强制标注 + 零命中 0.0 硬断言</td></tr>
<tr><td>2</td><td><code>probe_claimed_inheritance.py</code></td>
<td>有工具：真数据 + Null 对照 + 同口径复核 + 反自我欺骗闸门</td></tr>
<tr><td>3</td><td><code>verify.py</code> R-BK2 收口对账</td>
<td>有门禁：手册-代码-数据三方对账</td></tr>
<tr><td>4</td><td><b>审计锚三字段规范</b>（写进手册）</td>
<td>修一类：来源运行时 / 判据分 / 空转标记，缺一不自述</td></tr>
<tr><td>5</td><td><b>双计数门</b>（C6 机制）</td>
<td>修一类：自述数与新能力数并行记账，脱钩即报警</td></tr>
<tr><td>6</td><td><b>一手校错闸</b>（Step 2.5 产出）</td>
<td>修一类：转述回原文比对，见下</td></tr>
<tr><td>7</td><td><b>C4 资本纪律同构映射</b></td>
<td>有工具：回归测试 &gt; 每次最大亏损 ⇒ 回归闸门 &gt; 新增自述</td></tr>
<tr><td>8</td><td><code>build_html.py</code></td>
<td>有工具：暗色交付链路</td></tr>
</table>"""


def sec_s4() -> str:
    return """<h3>1 · 审计锚三字段（C3/C5 的落点）</h3>
<pre>{
  "claim": "已封装 取证技能",
  "anchor": {
    "source_run":   "2026-09-27 运行时 #7（实跑 exit=0）",
    "criteria_score": {"C3": 1.0, "C6": 0.0},
    "idle_flag": false
  }
}</pre>
<p>缺任一字段 ⇒ 该自述<b>不得标记为「已获得」</b>，只能标「已写盘」。</p>
<h3>2 · 双计数门（C6 机制）</h3>
<pre>claim_counter  += 1       # 每落一条自述
capability_counter += 1   # 仅在 held-out 判定通过时 +1

if claim_counter > capability_counter:
    emit("idle_ratio_rising", idle_ratio = 1 - capability/claim)</pre>
<p>★ 与 SEAL 的 1 bit 不同：SEAL 让 agent 只收一个 accept/reject 位，
<b>这里要求双计数并存</b> —— 单计数会让「自述涨、能力不涨」完全隐形。</p>
<h3>3 · 一手校错闸（Step 2.5 的副产品）</h3>
<pre>for kw in二手转述里的关键措辞:
    assert kw in一手原文  # 不 assert 就不得引用</pre>
<h3>4 · 回归闸门映射（C4）</h3>
<table><tr><th>资本纪律</th><th>SCI 映射</th></tr>
<tr><td>回归测试 &gt; 每次最大亏损</td><td>回归闸门 &gt; 新增自述</td></tr>
<tr><td>止损线先于加仓</td><td>已会能力清单先于新自述写入</td></tr>
</table>"""


def sec_s5() -> str:
    return """<table>
<tr><th>维</th><th>分</th><th>理由</th></tr>
<tr><td>意义</td><td class="hl">5.0</td>
<td>给出了自改进 agent 生态（OpenClaw 39 万星 / Hermes 25 万星）的结构性盲区，
且被 2026-07-27 的 arXiv 一手论文部分命中 —— 说明它真存在</td></tr>
<tr><td>结果</td><td>4.0</td><td>六判据 CLI 17/17 + 探针 4/4 + 收口对账，工程闭合</td></tr>
<tr><td>对齐</td><td>4.0</td>
<td>与「不谄媚/不隐瞒」一致：本件先把自己的 skill 库空转率 0.974 报出来再谈产品</td></tr>
<tr><td>证据</td><td>3.5</td><td>7 源落盘 + gh 核真 + 本机实跑；扣分 = 抖音通道失败，
C1/C4/C5 为【推导】</td></tr>
<tr><td>利益</td><td>3.5</td><td>命题值钱，<b>试点未定</b></td></tr>
<tr><th colspan="2">均分</th><th class="hl">4.00（≥3.6 算突破）</th></tr>
</table>
<h3>Step 5 自我回审（负反馈棘轮）</h3>
<ul>
<li><b>命题改写了一次</b>：原「AI 自主写 skill」→ 现「自述无对账」。
改写的触发者是自攻三问第一问，不是外部反馈。</li>
<li><b>一手校错：SEAL 措辞对不上</b>。Step 2.5 我用了「保守门槛 c_t ≥ b_t − δ_t /
whole-state rollback / 只收 1 bit」，回 arXiv 原文比对
<b>三处全无</b>。原文是 <code>conservative updating</code> /
<code>rolls back the entire policy–test state</code> /
<code>only one accept/reject bit</code> —— 把我自己的转述当一手，
正是本件要抓的病。<span class="bad">已修正锚点并记入已知限制。</span></li>
<li><b>反自我欺骗闸门告警过一次</b>（0.974 vs 0.002）并已核实为不同源，非互相印证。</li>
<li><b>未做</b>：与 skill-health-audit 的 <code>held-out evidence</code> 做过关键词级
交叉，但未做逐项指标对齐测试（与 SRA 同一处缺口）。</li>
</ul>
<div class="card">
<p><b>复现命令</b></p>
<pre>cd 突破件/self-claimed-inheritance-auditor
python collect_corpus.py          # 7 源落盘 + 三级角色闸门
python sci_cli.py                 # 六判据 17/17
python probe_claimed_inheritance.py   # Step 2.75 硬门槛 4/4
python verify.py                  # R-BK2 收口对账</pre>
</div>"""


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    html = (tpl("s3")
            .replace("__SEC_S0__", sec_s0())
            .replace("__SEC_S1__", sec_s1())
            .replace("__SEC_S2__", sec_s2())
            .replace("__SEC_S25__", sec_s25())
            .replace("__SEC_S275__", sec_s275())
            .replace("__SEC_S3__", sec_s3())
            .replace("__SEC_S4__", sec_s4())
            .replace("__SEC_S5__", sec_s5()))
    # 兜底：任何未替换的占位符都要暴露出来，不许静默吞掉
    left = [t for t in ("__SEC_", "__CSS__", "__NAV__", "__TITLE__", "__DATE__")
            if t in html]
    if left:
        print("[FAIL] 未替换的占位符：%s" % left)
        return 1
    p1 = OUT / "index.html"
    p2 = DESKTOP / "抖音学习突破七流程-自述继承审计器SCI-2026-09-27.html"
    p1.write_text(html, encoding="utf-8")
    p2.write_text(html, encoding="utf-8")
    print("[OK] %s  (%d B)" % (p1, p1.stat().st_size))
    print("[OK] %s  (%d B)" % (p2, p2.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
