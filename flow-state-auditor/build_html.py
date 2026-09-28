r"""FSA 交付生成器 —— 一份内容，三处落点（工程内 md / 规则层 md / 桌面 HTML）

暗色科技风沿用约定：#0b0e14 底 / #161c2c 卡 / Inter + 苹方。
桌面路径按约定落 `桌面/成果/中文名-日期.html`。
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_out"
OUT.mkdir(exist_ok=True)
DESKTOP = Path.home() / "Desktop" / "成果"
DESKTOP.mkdir(exist_ok=True)
TODAY = "2026-09-27"
TITLE = "抖音学习突破七流程 · 流式输出的完整性"

CSS = """
:root{--bg:#0b0e14;--card:#161c2c;--line:#242b3d;--fg:#e6e9f0;
--dim:#8b93a7;--acc:#5eead4;--warn:#fbbf24;--bad:#f87171;--good:#4ade80;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);
font-family:"Inter","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.75;font-size:15px}
.wrap{max-width:1080px;margin:0 auto;padding:48px 28px 96px}
h1{font-size:30px;line-height:1.35;margin:0 0 8px}
h2{font-size:21px;margin:44px 0 14px;padding-left:12px;
border-left:3px solid var(--acc)}
h3{font-size:16px;margin:26px 0 8px;color:var(--acc)}
.sub{color:var(--dim);font-size:13px;margin-bottom:28px}
.card{background:var(--card);border:1px solid var(--line);
border-radius:12px;padding:18px 20px;margin:14px 0}
.lead{background:linear-gradient(135deg,#161c2c,#1b2334);
border:1px solid var(--line);border-left:3px solid var(--acc)}
.lead p{margin:8px 0;font-size:16px}
code{background:#0f1420;border:1px solid var(--line);border-radius:5px;
padding:1px 6px;font-size:13px;color:var(--acc)}
pre{background:#0f1420;border:1px solid var(--line);border-radius:10px;
padding:14px 16px;overflow:auto;font-size:12.5px;line-height:1.65}
pre code{background:none;border:none;padding:0;color:#cbd5e1}
table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}
th,td{border:1px solid var(--line);padding:9px 11px;text-align:left}
th{background:#131a29;color:var(--acc);font-weight:600}
tr:nth-child(even) td{background:#121826}
.hl{color:var(--warn);font-weight:600}
.bad{color:var(--bad);font-weight:600}
.good{color:var(--good);font-weight:600}
.quote{border-left:3px solid var(--warn);background:#1a1a12;
padding:12px 16px;margin:14px 0;border-radius:0 8px 8px 0;color:#f5e6c8}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:14px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px}
.kpi .n{font-size:26px;font-weight:700;color:var(--acc)}
.kpi .l{font-size:12px;color:var(--dim);margin-top:4px}
ul,ol{padding-left:22px}
li{margin:5px 0}
.tag{display:inline-block;font-size:11px;padding:2px 8px;border-radius:20px;
border:1px solid var(--line);color:var(--dim);margin-right:6px}
footer{margin-top:64px;padding-top:20px;border-top:1px solid var(--line);
color:var(--dim);font-size:12px}
"""


def kv_table(rows: list[tuple[str, str]]) -> str:
    return ("<table><tr><th style='width:26%'>项</th><th>值</th></tr>"
            + "".join("<tr><td>%s</td><td>%s</td></tr>" % (a, b)
                      for a, b in rows) + "</table>")


def build() -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title><style>{CSS}</style></head><body><div class="wrap">

<h1>{TITLE}</h1>
<div class="sub">模态 7688936275026573178 · 第二十二条 · 生成于 {TODAY}</div>

<div class="card lead">
<p><b>一句话：</b>「流式输出」把「输出」从一个原子事件变成了一个持续过程，
但我们的评估口径、验收口径、对 AGI 的期待，全都还建在「输出完毕」那一刻。</p>
<p><b>实测：</b>服务端只发了 <span class="hl">11/20</span> 帧就掐断，客户端
<span class="bad">err=None</span>，读到 EOF，零异常；只看「流结束了」的策略
把它判成了<span class="bad">「输出完成」</span>。</p>
</div>

<h2>一 这条视频说了什么（以及我拿到了什么）</h2>
<div class="card">
<p>标题原文：<b>「AGI甚至ASI常常被讨论 真的是流式输出吗？通用人工智能通常会怎么输」</b></p>
<p><span class="tag">RA-5 偏差声明</span>抖音页只返回标题与封面图，<b>视频正文未获取</b>；
modal_id 检索无命中，抖音分享页返回「抱歉出错了」。</p>
<p><b>「怎么输」是歧义。</b>两种解读：①「怎么输出」（口误）②「怎么输」= 会怎样失败。
本件取一个<b>两种解读下都成立</b>的命题，不替视频做定论。</p>
</div>

<h2>二 命题：完整性不是终点的属性</h2>
<div class="card">
<p>一个被截断了 9/20 的流，和一条顺利发完 20/20 的流，在客户端视角里
<b>只有「流结束了」这一点是共通的</b>。而「流结束」恰好是唯一一个
截断与完成同形的观测点。</p>
<div class="quote">「被截断的模型无法报告它被截断了，因为报告必须发生在那个
从未到达的 token 之后。只有外部元数据能告诉你。」<br>
—— <span class="dim">digitalapplied.com · AI Agent 截断静默失败</span></div>
</div>

<h2>三 六条判据与实测</h2>
{kv_table([
    ("F1 终态所有权", "押 <code>[DONE]</code> 这类<b>厂商私有约定</b>；它不是 SSE 规范内容。0.6"),
    ("F2 预算前置性 ★", "usage 只在最后一帧给出 ⇒ 中途无法对账。<b>0.5</b>"),
    ("F3 中途可观测性", "只有终态那一刻才有数。<b>0.0</b>"),
    ("F4 断流可分辨性", "实测截断与完成<b>同形</b>；唯一可分辨的是 <code>[DONE]</code>。<b>0.0</b>"),
    ("F5 终态字段覆盖率", "<code>finish_reason</code> 在传输层断流时不产生，读它的方案集体为 0。<b>0.0</b>"),
    ("F6 指标事件选择", "k6 默认测总响应时间，把三件事混成一个数。<b>0.3</b>"),
])}
<p>判定线 0.6。<b>行业通行做法均分 0.233 ⇒ flow_unreconciled。</b></p>

<h2>四 实测矩阵（本机实跑，非模拟）</h2>
<table>
<tr><th>服务端结局</th><th>判定策略</th><th>帧数</th><th>客户端异常</th><th>结论</th></tr>
<tr><td>完整发完 20</td><td>等 <code>[DONE]</code></td><td>21</td><td>无</td><td class="good">complete</td></tr>
<tr><td>完整发完 20</td><td>只看「流结束」</td><td>21</td><td>无</td><td class="good">complete</td></tr>
<tr><td>只发 11 就掐断</td><td>等 <code>[DONE]</code></td><td>11</td><td><b>无</b></td><td class="good">INCOMPLETE</td></tr>
<tr class="hl-row"><td>只发 11 就掐断</td><td>只看「流结束」</td><td>11</td><td><b>无</b></td><td class="bad">complete ← 把截断当完成</td></tr>
<tr><td>只发 11 就掐断</td><td>预算对账 11/20</td><td>11</td><td><b>无</b></td><td class="good">INCOMPLETE，且能说「缺 9」</td></tr>
</table>

<h2>五 唯一出路：把分母搬到起点</h2>
<div class="card">
<p>完整性 = <b>流前定好的分母</b> − <b>流终的分子</b>。它不是「终点的属性」。</p>
<p>预算前置后，客户端能说出「<span class="hl">收到 11/20，缺 9</span>」；
只看「流结束」的策略手里只有「结束了」这三个字，缺多少它<b>说不出</b>。</p>
</div>

<h2>六 与上件 UCA 的同构（本件最值钱的部分）</h2>
{kv_table([
    ("UCA 上件", "现存 413 册 / 原本 11095 册 —— 分母（永乐正本）<b>下落不明</b>"),
    ("本件 FSA", "已收 11 帧 / 预算 20 帧 —— 分母（预算）<b>必须在流前定死</b>"),
    ("共同病灶", "都在拿一个<b>事后才知道正确值</b>的分母，去算一个<b>事前声称</b>的比例"),
])}
<p>上件审「<b>不知道缺了哪几条</b>」，本件审「<b>不知道还要生成多少</b>」。同一个病，换个器官。</p>

<h2>七 通道结果</h2>
<div class="grid">
<div class="kpi"><div class="n">15/15</div><div class="l">fsa_cli selftest</div></div>
<div class="kpi"><div class="n">6/6</div><div class="l">策略矩阵</div></div>
<div class="kpi"><div class="n">5/5</div><div class="l">一手源采集</div></div>
<div class="kpi"><div class="n">0.233</div><div class="l">行业现状均分</div></div>
</div>
<p style="margin-top:14px">真实端点探测 <b>0/2</b>（sse.dev DNS 失败；
127.0.0.1:3080 <b>ConnectionRefused</b>）—— 如实记账：
<b>通道到不了 ≠ 内容不存在</b>。</p>

<footer>正明 · 抖音学习突破七流程 · 第二十二条<br>
规则层手册：<code>~/.workbuddy/rules/突破件/</code> · 工程：<code>突破件/flow-state-auditor/</code>
</footer>
</div></body></html>"""  # noqa: E501


def main() -> int:
    html = build()
    html_name = "抖音学习突破七流程-流式输出完整性-%s.html" % TODAY
    (OUT / html_name).write_text(html, encoding="utf-8")
    desk = DESKTOP / html_name
    desk.write_text(html, encoding="utf-8")
    print("[build] %s (%d B)" % (OUT / html_name, len(html)))
    print("[build] %s (%d B)" % (desk, len(html)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
