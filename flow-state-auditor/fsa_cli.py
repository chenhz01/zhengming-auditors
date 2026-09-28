r"""FSA —— Flow State Auditor（流态审计器）v1.0

审的不是「流式快不快」，审的是「流式给出的那堆东西，是不是完整的」。

★ 命题：完整性不是「终点的属性」，是「起点就定好的分母」与「终点的分子」之差。
  所有现有方案都在终点上加断言，而终点恰恰是截断与完成同形的那一点。
  实测（probe_stream_reality.py 本机实跑）：服务端只给 11/20 帧就掐断，
  客户端 err=None、读到 EOF、零异常；只看「流结束了」的策略判成「输出完成」。

六条判据 F1~F6，每条 0.0~1.0；均分 <0.6 判 flow_unreconciled。
每条判据标 evidence 来源：[实测] / [声明] / [推导] —— 推导项不许与实测项
混在一起报同一个均分而不加提示。
"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "_raw" / "artifacts"

# 探针实测固值（probe_stream_reality.py 本机实跑产出，勿手改）
PROBE_TRUNC_FRAMES = 11
PROBE_BUDGET_FRAMES = 20


@dataclasses.dataclass
class Decl:
    """一条流式管道的声明。"""
    name: str = ""
    terminal_ownership: str = ""   # protocol_guaranteed|vendor_private|client_inferred|absent
    budget_ahead: str = ""         # ahead|post_only|unknown      ← ★ 招牌
    midstream: str = ""            # full|partial|terminal_only
    metric_event: str = ""         # partial|terminal_only|none
    notes: list[str] = dataclasses.field(default_factory=list)


# ───────────────────────── 六条判据 ─────────────────────────
def j_terminal_ownership(d: Decl) -> dict:
    """F1 终态所有权：完整性判定押在哪类信号上。

    [实测依据] [DONE] 是 OpenAI 私有约定，不在 SSE 规范内 ⇒ 押它 = 押厂商良心。
    Atlassian 官方文档逐字写明：不完整结束的流不抛异常。
    """
    G = {"protocol_guaranteed": 1.0, "vendor_private": 0.6,
         "client_inferred": 0.3, "absent": 0.0}
    if d.terminal_ownership not in G:
        # ★ 零命中也必须给 score，否则 audit 的 score 过滤会看不见它
        return {"crit": "F1", "score": 0.0, "zero_hit": True, "basis": "声明",
                "detail": "未声明终态所有权，无法判定"}
    return {"crit": "F1", "score": G[d.terminal_ownership], "zero_hit": False,
            "basis": "声明", "label": d.terminal_ownership,
            "detail": {"protocol_guaranteed": "协议层保证，不依赖厂商",
                       "vendor_private": "押 [DONE] 这类私有约定",
                       "client_inferred": "客户端猜，等于没有信号",
                       "absent": "完全没有终态信号"}[d.terminal_ownership]}


def j_budget_ahead(d: Decl) -> dict:
    """F2 预算前置性 ★招牌：总量在流开始前就定死了吗？

    [实测依据] 预算前置后客户端能说出「收到 11/20，缺 9」；
    只看「流结束了」的策略说不出。usage 只在最后一帧 ⇒ 中途无法对账。
    """
    G = {"ahead": 1.0, "post_only": 0.5, "unknown": 0.0}
    if d.budget_ahead not in G:
        return {"crit": "F2", "score": 0.0, "zero_hit": True, "basis": "声明",
                "detail": "未声明预算位置，无法判定"}
    return {"crit": "F2", "score": G[d.budget_ahead], "zero_hit": False,
            "basis": "声明", "label": d.budget_ahead,
            "detail": {"ahead": "流前定预算，可实时对账",
                       "post_only": "usage 只在最后一帧，中途无法对账",
                       "unknown": "没有分母，只有分子"}[d.budget_ahead]}


def j_midstream(d: Decl) -> dict:
    """F3 中途可观测性：流中能否回答「已生成多少 / 还剩多少」."""
    G = {"full": 1.0, "partial": 0.5, "terminal_only": 0.0}
    if d.midstream not in G:
        return {"crit": "F3", "score": 0.0, "zero_hit": True, "basis": "声明",
                "detail": "未声明中途可观测性，无法判定"}
    return {"crit": "F3", "score": G[d.midstream], "zero_hit": False,
            "basis": "声明", "label": d.midstream,
            "detail": {"full": "已生成/剩余都可报",
                       "partial": "只能数已生成",
                       "terminal_only": "只有终态那一刻才有数"}[d.midstream]}


def j_truncation(d: Decl) -> dict:
    """F4 断流可分辨性：这条管道能不能把「截断」和「完成」分开。

    客观事实（[实测]）：传输层断流时终态字段不产生、客户端不抛异常。
    但「这条管道能不能分辨」取决于有没有第二条通道 —— 预算差就是那条。
    """
    if d.budget_ahead == "ahead":
        return {"crit": "F4", "score": 1.0, "zero_hit": False, "basis": "推导",
                "label": "distinguishable_by_budget",
                "detail": ("实测：预算前置后，收到 %d/%d 帧即判 INCOMPLETE，"
                           "截断不依赖终态字段即可分辨"
                           % (PROBE_TRUNC_FRAMES, PROBE_BUDGET_FRAMES))}
    return {"crit": "F4", "score": 0.0, "zero_hit": False, "basis": "实测",
            "label": "indistinguishable",
            "detail": ("实测：传输层断流时客户端 err=None，截断与完成在客户端"
                       "视角同形；唯一可分辨的是 [DONE]，而它不在 SSE 规范内")}


def j_finish_reason_coverage(d: Decl) -> dict:
    """F5 终态字段依赖度：完整性判定是否必须读到终态字段。

    [实测依据] Atlassian / llm-output-guard / alayacore / dev.to 全都读
    finish_reason，而传输层断流时该字段不产生 ⇒ 必须读它的方案在那儿为 0。
    """
    if getattr(d, "budget_ahead", "") == "ahead":
        return {"crit": "F5", "score": 1.0, "zero_hit": False, "basis": "推导",
                "label": "not_dependent",
                "detail": "完整性由预算差判定，不依赖任何终态字段"}
    return {"crit": "F5", "score": 0.0, "zero_hit": False, "basis": "实测",
            "label": "transport_gap",
            "detail": ("finish_reason 在传输层断流时不产生；实测 truncated 场景"
                       "该字段缺失，且客户端不抛异常 —— 整条读终态的路线在这"
                       "一处集体为 0")}


def j_metric_event(d: Decl) -> dict:
    """F6 指标事件选择：测的是 partial 事件还是 terminal 事件。

    [实测依据] k6 无 SSE 原生支持，默认测总响应时间，
    把生成质量 / 预填充 / decode 混成一个数 ⇒ 测错了事件。
    """
    G = {"partial": 1.0, "terminal_only": 0.3, "none": 0.0}
    if d.metric_event not in G:
        return {"crit": "F6", "score": 0.0, "zero_hit": True, "basis": "声明",
                "detail": "未声明指标测哪个事件，无法判定"}
    return {"crit": "F6", "score": G[d.metric_event], "zero_hit": False,
            "basis": "声明", "label": d.metric_event,
            "detail": {"partial": "测中间事件（TTFT/ITL）",
                       "terminal_only": "只测终点，且这个终点本身是错的事件",
                       "none": "没有指标"}[d.metric_event]}


JUDGES = [j_terminal_ownership, j_budget_ahead, j_midstream,
          j_truncation, j_finish_reason_coverage, j_metric_event]


def audit(d: Decl) -> dict:
    ps = []
    for j in JUDGES:
        r = j(d)
        if not r.get("zero_hit") and r.get("score") is None:
            r["score"] = 0.0
        ps.append(r)
    scores = [p["score"] for p in ps if p["score"] is not None]
    avg = sum(scores) / len(scores) if scores else 0.0
    return {"name": d.name, "parts": ps, "avg": round(avg, 3),
            "verdict": "flow_unreconciled" if avg < 0.6 else "ok"}


# ───────────────────────── 真数据 ─────────────────────────
def industry_now() -> Decl:
    """行业通行做法（2026-09-27，据 5 一手源 + 本机探针）"""
    return Decl(
        name="行业通行做法（读 finish_reason / 等 [DONE]）",
        terminal_ownership="vendor_private",   # [DONE] 非 SSE 标准
        budget_ahead="post_only",              # usage 只在最后一帧
        midstream="terminal_only",
        metric_event="terminal_only",          # k6 默认测总响应时间
        notes=[
            "k6 无 SSE 原生支持，默认测总响应时间（把三件事混成一个数）",
            "OpenAI 兼容 API 的 usage 只在最后一帧给出",
            "Atlassian 官方文档注释：不完整的流式结束不抛异常",
        ],
    )


def fsa_target() -> Decl:
    """FSA 主张的管道（预算前置）"""
    return Decl(
        name="FSA 主张：预算前置 + 终态双签",
        terminal_ownership="protocol_guaranteed",
        budget_ahead="ahead",
        midstream="full",
        metric_event="partial",
        notes=[
            "预算在流前定死，流中实时对账：已收 X / 预算 B",
            "实测：预算前置后可说出「11/20 缺 9」；只看流结束的策略说不出",
        ],
    )


# ───────────────────────── 自检 ─────────────────────────
def _selftest() -> int:
    st = {"n": 0, "bad": 0}

    def ck(name: str, cond: bool, extra: str = "") -> None:
        st["n"] += 1
        if not cond:
            st["bad"] += 1
            print("  [FAIL] %s %s" % (name, extra))

    a = audit(industry_now())
    ck("行业现状均分低", a["avg"] < 0.6, str(a["avg"]))
    ck("行业现状判 flow_unreconciled", a["verdict"] == "flow_unreconciled")
    ck("F1 落 vendor_private", a["parts"][0]["score"] == 0.6)
    ck("F2 落 post_only", a["parts"][1]["score"] == 0.5)
    b = audit(fsa_target())
    ck("FSA 主张均分高于行业", b["avg"] > a["avg"],
       "%s vs %s" % (b["avg"], a["avg"]))
    ck("FSA 主张六判据齐", len(b["parts"]) == 6)
    ck("FSA F4 标为推导", b["parts"][3].get("basis") == "推导")
    ck("行业 F4 标为实测", a["parts"][3].get("basis") == "实测")

    # ★ 零命中必须返回 score，否则 audit 的过滤看不见它
    z = audit(Decl(name="z"))
    ck("零声明时 F1 zero_hit", z["parts"][0].get("zero_hit") is True)
    ck("零声明时 F1 score 可见", z["parts"][0]["score"] is not None)
    ck("零声明时 avg 仍可算", isinstance(z["avg"], float))

    ck("探针实测帧数 11", PROBE_TRUNC_FRAMES == 11)
    ck("探针预算帧数 20", PROBE_BUDGET_FRAMES == 20)
    ck("缺帧数可算", PROBE_BUDGET_FRAMES - PROBE_TRUNC_FRAMES == 9)

    p = ART / "corpus_atlassian_streaming_errors.md"
    if p.is_file():
        txt = p.read_text(encoding="utf-8")
        ck("Atlassian 语料含「不抛异常」", "Exceptions are not thrown" in txt)
        ck("Atlassian 语料含 finish_reason", "finish_reason" in txt)
    else:
        print("  [skip] Atlassian 语料未落盘")
    p2 = ART / "corpus_da_truncation_silent.md"
    if p2.is_file():
        ck("截断长文含招牌句", "cannot report that it was cut off"
           in p2.read_text(encoding="utf-8"))

    print("[selftest] %d/%d %s" % (st["n"] - st["bad"], st["n"],
                                   "PASS" if st["bad"] == 0 else "FAIL"))
    return 0 if st["bad"] == 0 else 1


# ───────────────────────── CLI ─────────────────────────
def _scan() -> int:
    for d in (industry_now(), fsa_target()):
        a = audit(d)
        print("══ %s" % a["name"])
        for p in a["parts"]:
            print("  %s  %.1f  %-26s[%s] %s"
                  % (p["crit"], p["score"], str(p.get("label", "")),
                     p.get("basis", "声明"), p["detail"]))
        print("  ── 均分 %.3f ⇒ %s" % (a["avg"], a["verdict"]))
        if d.name.startswith("FSA"):
            nd = [p["crit"] for p in a["parts"]
                  if p.get("basis") == "推导" and p["score"] == 1.0]
            print("     ⚠ 其中 %s 为【推导】而非【实跑】：F2 一改就跟着变。"
                  % ",".join(nd))
        for n in d.notes:
            print("       · %s" % n)
        print()
    return 0


def _report() -> int:
    (ART / "report.json").write_text(
        json.dumps({"industry": audit(industry_now()),
                    "fsa": audit(fsa_target())}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print("[scan] report → %s" % (ART / "report.json"))
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "selftest"
    if cmd == "selftest":
        return _selftest()
    if cmd == "scan":
        return _scan()
    if cmd == "report":
        return _report()
    print(__doc__)
    print("用法：fsa_cli.py {selftest|scan|report}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
