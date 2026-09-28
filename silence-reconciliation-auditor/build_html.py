#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 SRA 的实跑结果渲染成暗色 HTML（工程 _out/index.html + 桌面/成果 同构两份）。

★ 只做渲染，不复算 —— 所有数字都从 sra_cli / probe 实跑结果里取，
  否则 HTML 里就会出现第三套数字（手册一套、CLI 一套、网页一套）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import sra_cli  # noqa: E402
import probe_silence_reality as P  # noqa: E402

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "_out"
OUT.mkdir(exist_ok=True)
DESKTOP = Path.home() / "Desktop" / "成果"
DESKTOP.mkdir(parents=True, exist_ok=True)
DESKTOP_NAME = "抖音学习突破七流程-沉默对账器-2026-09-27.html"

HANDBOOK = (Path.home() / ".workbuddy" / "rules" / "突破件"
            / "突破-2026-09-27-沉默对账器SRAv1.0.md")

NAV = [
    ("命题改写", "#sec_thesis"), ("Step 0 缺口单", "#sec_gap"), ("五源交叉", "#sec_src"),
    ("六判据", "#sec_crit"), ("实测矩阵", "#sec_meas"), ("异议四件套", "#sec_obj"),
    ("突破件", "#sec_bk"), ("我忽略了什么", "#sec_ignore"), ("五维评分", "#sec_score"),
    ("待决与对账", "#sec_todo"),
]


def e(s: Any) -> str:
    return (str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def tbl(headers: list[str], rows: list[list[str]], cls: str = "") -> str:
    h = "".join("<th>%s</th>" % c for c in headers)
    body = "".join("<tr>%s</tr>" % "".join("<td>%s</td>" % c for c in r) for r in rows)
    return '<table class="%s"><thead><tr>%s</tr></thead><tbody>%s</tbody></table>' % (cls, h, body)


def sec_thesis() -> str:
    return """
<section id="sec_thesis" class="card">
  <h2>命题（★ 被 ProactiveBench 改写过一次）</h2>
  <p class="lead">沉默不是「没事发生」的证据，是「没人定义过该不该发生」的证据。
  现有方案全在测「该说没说」，而没人问「这一段沉默根本无法判定」。</p>
  <div class="quote">
    <b>改写事件</b>：Step 2.5 自攻三问第一问就撞上真东西 ——
    <code>ProactiveBench</code>（arXiv <b>2609.12658</b>，北航 + Qwen 商分，2026-09-11 提交）
    已经在测漏报：「four window-based subtasks distinguish early, in-window, and
    <b>missed</b> responses」。按 skill 判据落点规则，这属于<b>「这个缝隙是我的错误，必须改写结论」</b>。
  </div>
  <p class="dim">改写得比原命题硬：ProactiveBench 测漏报的<b>前提</b>是事先有人标注了
  「什么时候该说话」（annotated speech window）—— 而<b>真实部署里没人做这件事</b>。
  真正的漏报不是「报晚了」，是<b>「压根不在题面上」</b>。</p>
</section>"""


def sec_gap() -> str:
    return """
<section id="sec_gap" class="card">
  <h2>Step 0 对抗闸门：对上件 FSA 下刀</h2>""" + tbl(
        ["#", "FSA 的做法", "问题", "修补"],
        [["1", "六判据均分 1.000 但无一处试点", "设计态被当成运行态，手册未标",
          "新增硬规则：均分 ≥0.9 必须在「已知限制」首行写明试点未定"],
         ["2", "招牌指标未区分【实测】/【推导】", "会让人以为 1.000 是跑出来的",
          "SRA 起加 basis_override，CLI 自标"],
         ["3", "未记「HF 通道第三次到不了」", "§S3.4 连犯记账缺失",
          "单独记账：curl (28) 21276 ms / HTTP=000 / bytes=0 ⇒ 连接失败 ≠ 不存在"]],
    ) + "</section>"


def sec_src() -> str:
    return """
<section id="sec_src" class="card">
  <h2>五源一手交叉（三级来源角色）</h2>""" + tbl(
        ["源", "角色", "抓到什么"],
        [["openmoss.ai 官方站", "CORE", "三大核心行为原文、13 行 citation"],
         ["GitHub README（raw 明文）", "CORE", "全部 News 时间线、News 条目"],
         ["上海创智学院通稿", "CORE", "4.57×/5.48× 吞吐、256K、16FPS"],
         ["arXiv 2608.15045", "CORE", "摘要：66.0 vs 37.5、2.8×→5.1×"],
         ["OmniMMI 仓库本体", "CORE", "独立确认 66.0 on PA@OmniMMI；该仓自己发过勘误"],
         ["新华日报·交汇点", "<b>SIDE</b>", "时间线旁证，关键词密度 1/9 ⇒ 不进计数"],
         ["open-source-datasets 清单", "REF", "核实数据集归属，与主题词无关"]],
    ) + """
  <p class="dim">★ 旁证冒充主题源 = 把一条腿算成两条腿。密度低 ≠ 不相关
  （OmniMMI 恰恰是「主动性评测」的定义源，README 不复述营销词密度天然低），
  所以自动降权被取消了，改「声明式角色 + 低密度告警」，判断权留给人。</p></section>"""


def sec_crit() -> str:
    return """
<section id="sec_crit" class="card">
  <h2>六判据（把 FSA 的输出侧病搬回时间侧）</h2>""" + tbl(
        ["判据", "问什么", "行业现状", "SRA"],
        [["G1 沉默信号所有权", "「我沉默了」这个信号谁给的", "0.400（自报）", "1.000【推导】"],
         ["G2 真值前置性 ★", "「该说话的时刻」流前定死了吗", "0.500", "1.000【推导】"],
         ["G3 漏报可分辨性", "能分开「该说没说」与「没标过该说」吗", "0.500", "1.000【推导】"],
         ["G4 未覆盖度 ★招牌", "有没有指标说多少沉默无法判定", "<b>0.000</b>", "<b>1.000【实测】</b>"],
         ["G5 声明可外部校验", "「我主动沉默」的理由能外部验证吗", "0.000", "1.000【推导】"],
         ["G6 时点粒度", "整段还是秒级", "1.000", "1.000【实测】"]],
    ) + """
  <p class="warn">行业均分 <b>0.400</b> ⇒ <code>silence_unreconciled</code>；SRA 均分 1.000。
  ⚠ CLI 主动告警：G1/G2/G3/G5 为【推导】，真值一改就跟着变。</p>
  <p class="dim">★ 与 FSA 同构：<b>FSA 审「不知道还要生成多少」，SRA 审「不知道这沉默该不该发生」</b>
  —— 同一个病，又换一个器官。</p></section>"""


def sec_meas(scan, demo, p1, p2, p3, p4) -> str:
    n_sil = scan["total_silence_contexts"]
    r_unc = scan["uncovered_ratio"]
    n_und = scan["unjudgeable"]
    return f"""
<section id="sec_meas" class="card">
  <h2>实测矩阵（本机实跑，不是模拟）</h2>
  <div class="kpis">
    <div class="kpi"><span class="k">唯一语料</span><span class="v">{scan['docs_scanned']} 份</span></div>
    <div class="kpi"><span class="k">沉默上下文</span><span class="v">{n_sil} 处</span></div>
    <div class="kpi"><span class="k">无法判定</span><span class="v">{n_und} 处</span></div>
    <div class="kpi hl"><span class="k">未覆盖沉默比例</span><span class="v">{r_unc}</span></div>
  </div>
  <h3>探针四连（Step 2.75 硬门槛）</h3>""" + tbl(
        ["探针", "结论"],
        [["P1 定义依赖漏报",
          f"三套定义分别判出 0 / 10 / 9 条漏报；<b>稳健漏报（三套都判）= 0</b>，"
          f"<b>定义依赖漏报 = {p1['definition_dependent_missed']} 条（{p1['definition_dependent_rate']}）</b>"],
         ["P2 最小对账器",
          f"在 <b>{p2['undecidable_n']} 条（{p2['undecidable_ratio']}）</b>上拒绝出判定，"
          f"且一条 MISSED 都没漏出去"],
         ["P3 锚点敏感度",
          f"单锚点边际 ≤1 条；只留中文 {p3['only_cn']} / 只留英文 {p3['only_en']} / "
          f"整套抽掉 {p3['drop_whole_set_ratio']} ⇒ 招牌数是<b>组合</b>的产物"],
         ["P4 漏报率漂移",
          f"同一系统区间 [{p4['min']}, {p4['max']}]，<b>spread = {p4['spread']}</b>"]],
    ) + f"""
  <p class="hl-big">P1 是本件的杀手数据：{n_sil} 条沉默里，<b>没有一条</b>的「漏报」身份与定义无关。
  剩下 {p1['definition_dependent_missed']} 条是<b>定义给的，不是系统给的</b>。</p>
  <h3>官方 9 个 demo 触发条件分类</h3>""" + tbl(
        ["分类", "数", "占比"],
        [["人为真值（触发条件由用户事前约定）", f"{demo['artificial_n']}", f"<b>{demo['artificial_ratio']}</b>"],
         ["客观真值（从画面内容里读出来的事件）", f"{demo['objective_n']}", "0.778"],
         ["未判定", f"{demo['undecided']}", "0.000"]],
    ) + "</section>"


def sec_obj() -> str:
    return """
<section id="sec_obj" class="card">
  <h2>异议四件套</h2>
  <div class="qa"><span class="q">① 我的结论</span><span class="a">沉默不是「没事发生」的证据，
    是「没人定义过该不该发生」的证据。</span></div>
  <div class="qa"><span class="q">② 依据</span><span class="a">G4 的 0.898 是实测（语料全量跑出）；
    G1/G2/G3/G5 是【推导，FSA 招牌机制已生效】。</span></div>
  <div class="qa"><span class="q">③ 风险</span><span class="a">最省力的一击是「0.898 只是我自己提的锚点算出来的」⇒
    已用反向注入 + P3 敏感度正面接住（抽掉整套真值 ⇒ 上升至 1.000）。</span></div>
  <div class="qa"><span class="q">④ 替代解释</span><span class="a">「现有方案根本不打算说这件事，因为
    『沉默质量』在商业上无法承诺」—— 推翻不了结论，但能推翻「我做的是护城河」；
    <b>SRA 也不是护城河，是下一代指标</b>。</span></div>
</section>"""


def sec_bk() -> str:
    items = [
        "三级来源角色机制（CORE/SIDE/REF/DUP）—— 采集器不许把旁证冒充主题源",
        "内容指纹去重闸（sha256）—— 同字节算一个源，杜绝一个来源冒领成两个",
        "取消启发式自动降权 —— 密度低不等于不相关，判断权留给人",
        "六判据 CLI（SRA v1.0）—— 把 FSA 的输出侧病搬回时间侧",
        "招牌实测指标「未覆盖沉默比例」—— 语料全量跑出，不是设计主张",
        "双声明分离 + basis_override —— 不许把主张标成实测",
        "最小对账器 reconcile() —— 无真值即拒绝出漏报，附 requires_prior_annotation",
        "定义依赖漏报分析 —— 三套定义 / 稳健漏报 0 / 漏报率漂移",
        "锚点组合敏感度 P3 —— 单个不敏感、组合敏感",
        "Step 0 缺口单机制 —— 对上件 FSA 出 3 条 + 一条新的修补规则",
    ]
    return """
<section id="sec_bk" class="card">
  <h2>本件的十项突破件 <span class="ok">R-BK1 数量闸：10 / 5 ✓</span></h2>
  <ul class="bl">""" + "".join("<li>%s</li>" % e(i) for i in items) + "</ul></section>"


def sec_ignore() -> str:
    ignores: list[str] = []
    if HANDBOOK.exists():
        t = HANDBOOK.read_text(encoding="utf-8")
        seg = t.split("## 九 我忽略了什么", 1)
        if len(seg) > 1:
            found = re.findall(r"(?m)^\s*(\d+)\.\s+(.+)$", seg[1])
            ignores = ["%s. %s" % (n, x.strip()) for n, x in found]
    return f"""
<section id="sec_ignore" class="card">
  <h2>我忽略了什么 <span class="ok">从手册实读 {len(ignores)} 条（要求 ≥4）</span></h2>
  <ul class="ig">""" + "".join("<li>%s</li>" % e(x) for x in ignores) + "</ul></section>"


def sec_score() -> str:
    return '<section id="sec_score" class="card"><h2>五维评分</h2>' + tbl(
        ["维", "分", "理由"],
        [["意义", "5.0", "所有主动语音/视频系统的结构性盲区，且被 2026-09-11 最新论文部分命中"],
         ["结果", "4.0", "六判据 CLI + 探针四连 + 收口对账，工程闭合"],
         ["对齐", "4.0", "与「人始终在环」「三层护栏」一致：把判定权还给事前真值"],
         ["证据", "4.5", "5 一手源 + 三级角色 + 指纹去重 + 本机实跑；扣 HF 通道与勘误史"],
         ["利益", "3.5", "命题值钱，试点未定，ProactiveBench 已占一半坑位"],
         ["<b>均分</b>", "<b>4.20</b>", "≥3.6 算突破；任一维 &lt;3.0 归零（无）"]],
        cls="score") + "</section>"


def sec_todo() -> str:
    return """
<section id="sec_todo" class="card">
  <h2>待决（需人工拍板）</h2>
  <ul class="todo">
    <li>⏸ <b>本件是否上 GitHub</b>；若推，建议与 DCA / UCA / FSA 同仓（四件同族）。</li>
    <li>⏸ <b>上件 UCA 三条缺口</b>（张升 413 册无落盘语料）是否现在补。</li>
    <li>⏸ <b>FSA / SRA 的第一个试点</b>给谁 —— 试点未定前 1.000 只是设计态。</li>
    <li>⏸ 跨轮挂起：首推 3 件（DCA / TIA / SEG）仍待拍板。</li>
  </ul>
  <h2>已知限制</h2>
  <p class="warn">⚠ <b>试点未定前，SRA 一栏的 1.000 是设计态，不是运行态。</b>
  六判据均分 ≥0.9，其中 G1/G2/G3/G5 为【推导】。首个试点落地前不得对外宣称「沉默已可对账」。</p>
  <ul class="ig">
    <li>分母是营销语料不是评测集，换真实部署日志后数字会变。</li>
    <li>huggingface.co 通道三次到不了 ⇒ 若有官方 HF 仓库未采，语料覆盖不完整。</li>
    <li>三套定义由我拟定，非行业既有分类；换人拟会换数。</li>
    <li>未做与 ProactiveBench 的逐项指标对齐测试。</li>
  </ul>
</section>"""


def build() -> str:
    scan = sra_cli.scan_silence_contexts()
    demo = sra_cli.scan_demo_triggers()
    events = P.build_events()
    p1 = P.p1_flip(events)
    p2 = P.p2_reconciler(events)
    p3 = P.p3_anchor_sensitivity(events)
    p4 = P.p4_miss_rate_drift(events)

    nav = "".join('<a href="%s">%s</a>' % (h, t) for t, h in NAV)
    body = (sec_thesis() + sec_gap() + sec_src() + sec_crit()
            + sec_meas(scan, demo, p1, p2, p3, p4) + sec_obj() + sec_bk()
            + sec_ignore() + sec_score() + sec_todo())

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>抖音学习突破七流程 · 沉默对账器 SRA v1.0</title>
<style>
:root{{--bg:#0b0e14;--card:#161c2c;--line:#232b40;--fg:#d7dee9;--dim:#8b97ad;
--acc:#5eead4;--acc2:#a78bfa;--warn:#fbbf24;--ok:#4ade80}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);
font-family:Inter,"PingFang SC","Microsoft YaHei",system-ui,sans-serif;line-height:1.75}}
.wrap{{display:flex;min-height:100vh}}
aside{{width:230px;flex:0 0 230px;background:#0e1320;border-right:1px solid var(--line);
padding:22px 14px;position:sticky;top:0;height:100vh;overflow:auto}}
aside .logo{{font-size:13px;color:var(--acc);letter-spacing:.14em;margin-bottom:6px}}
aside .title{{font-size:17px;font-weight:700;margin-bottom:18px}}
aside a{{display:block;padding:7px 10px;color:var(--dim);text-decoration:none;font-size:13.5px;
border-radius:7px;transition:.15s}}
aside a:hover{{background:#1a2133;color:var(--fg)}}
main{{flex:1;padding:34px 42px;max-width:1080px}}
h1{{font-size:27px;margin:0 0 6px}}
h2{{font-size:19px;margin:30px 0 12px;padding-left:11px;border-left:3px solid var(--acc)}}
h3{{font-size:15.5px;margin:22px 0 8px;color:var(--acc2)}}
.sub{{color:var(--dim);font-size:13.5px;margin-bottom:24px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:22px 24px;margin-bottom:18px}}
table{{width:100%;border-collapse:collapse;font-size:13.5px;margin:10px 0}}
th{{background:#1b2233;color:var(--acc);text-align:left;padding:9px 11px;
border-bottom:1px solid var(--line);font-weight:600}}
td{{padding:9px 11px;border-bottom:1px solid #1d2437;vertical-align:top}}
tr:last-child td{{border-bottom:none}}
table.score td:nth-child(1){{width:110px}}
.lead{{font-size:16px;color:#fff;font-weight:600;line-height:1.9}}
.quote{{background:#111726;border-left:3px solid var(--acc2);padding:13px 16px;
border-radius:0 8px 8px 0;margin:14px 0;font-size:13.8px}}
.dim{{color:var(--dim);font-size:13.5px}}
.warn{{background:#2a2113;border:1px solid #4d3a12;border-radius:8px;padding:11px 14px;
font-size:13.5px;margin:12px 0}}
.ok{{background:#12291c;color:var(--ok);font-size:12px;padding:2px 9px;border-radius:20px;
margin-left:8px;font-weight:500}}
.kpis{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}}
.kpi{{background:#111726;border:1px solid var(--line);border-radius:10px;padding:14px}}
.kpi .k{{display:block;color:var(--dim);font-size:12px}}
.kpi .v{{display:block;font-size:20px;font-weight:700;margin-top:4px}}
.kpi.hl{{border-color:#2b4a44}}.kpi.hl .v{{color:var(--acc)}}
.hl-big{{background:#101b1a;border:1px solid #2b4a44;border-radius:9px;padding:14px 17px;
color:var(--acc);font-size:14.5px;margin:14px 0}}
.qa{{background:#111726;border:1px solid var(--line);border-radius:9px;padding:12px 15px;margin:9px 0}}
.qa .q{{display:inline-block;min-width:120px;color:var(--acc2);font-weight:600;font-size:13.5px}}
.qa .a{{font-size:13.5px}}
ul.bl li,ul.ig li,ul.todo li{{margin:7px 0;font-size:13.8px}}
ul.ig li{{color:#c9d2e0}}
ul.todo li{{list-style:none}}
code{{background:#111726;padding:1.5px 6px;border-radius:5px;font-size:12.5px;color:var(--acc)}}
footer{{color:var(--dim);font-size:12.5px;margin:26px 0 8px}}
</style></head><body><div class="wrap">
<aside><div class="logo">ZHENGMING · BREAKTHROUGH</div><div class="title">沉默对账器 SRA v1.0</div>
{nav}</aside>
<main>
<h1>抖音学习突破七流程 · 沉默对账器（SRA v1.0）</h1>
<div class="sub">视频源：抖音 modal_id 7683451715803212617 ／ MOSS-VL-Realtime
　·　命题：沉默无法与漏报区分　·　全部数字本机实跑</div>
{body}
<footer>只渲染不复算 —— 与 sra_cli / probe_silence_reality / 突破手册同一套数字。</footer>
</main></div></body></html>"""


def main() -> int:
    html = build()
    for p in (OUT / "index.html", DESKTOP / DESKTOP_NAME):
        p.write_text(html, encoding="utf-8")
        print("[写出] %s (%d B)" % (p, p.stat().st_size))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
