#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
LGA 自检套件。

纪律（来自第八件 SEA 收尾自查的两个真 bug）：
  1. 每条断言都必须是**可能被判否**的。禁止 `rc in (0, 2)` 这类"永远为真"的空断言。
  2. 每条断言写完自问一遍：它有没有可能永远为真？有没有实际在守着某个行为？
  3. 口径类的东西提成具名函数（lga_exit_code / summarize），逐档断言，不留没覆盖的分支。

用法： python verify.py
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = __file__.rsplit("\\", 1)[0] if "\\" in __file__ else __file__.rsplit("/", 1)[0]
sys.path.insert(0, HERE)

import lga_cli  # noqa: E402

PASS = 0
FAIL = 0
_lines: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        _lines.append(f"  [PASS] {name}")
    else:
        FAIL += 1
        _lines.append(f"  [FAIL] {name}" + (f"  <- {detail}" if detail else ""))


def run_cli(args: list[str]) -> tuple[int, str]:
    p = subprocess.run([sys.executable, f"{HERE}/lga_cli.py", *args],
                       capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    # ---------------------------------------------------------------- 切条
    md = """# 租房避坑

- 打开贝壳找房，筛选整租
- 核对房东身份证与房产证是否一致
- ```python
  print("这种整块代码块不该被当成条目")
  ```
- 要注意保持健康的生活习惯
- 超过 30 平并且租金低于 3000 元就可以考虑
"""
    items = lga_cli.extract_items(lga_cli.strip_fences(md))
    check("能从 Markdown 切出 4 条列表项（代码块已剔除）", len(items) == 4, f"实际 {len(items)} 条")
    check("标题不计入条目数", not any(i["text"].startswith("#") for i in items))
    check("条目挂在正确的 section 上", items and items[0]["section"] == "租房避坑")

    # 回归：围栏开在列表项里（"- ```python"）时，后面同级的条目不能被吞掉。
    # v1.0 第一版这里只认行首围栏，结果"要注意…"和"超过 30 平…"两条凭空消失。
    texts = [i["text"] for i in items]
    check("围栏写在列表项里不会吞掉后续条目",
          any("要注意保持健康" in t for t in texts) and any("超过 30 平" in t for t in texts),
          str(texts))

    # ---------------------------------------------------------------- 裸话识别
    vague = lga_cli.score_item({"text": "要注意保持健康的生活习惯", "section": ""})
    check("纯形容词条目判为不可执行", vague["actionable"] is False)
    check("纯形容词条目被标为裸话", vague["vague_only"] is True)

    act_with_crit = lga_cli.score_item({"text": "打开贝壳找房筛选整租，如果超过30天没回复就换一家", "section": ""})
    check("动作 + 对象 + 判据 => 可执行且闭环",
          act_with_crit["actionable"] and act_with_crit["closure"] is True)

    act_no_crit = lga_cli.score_item({"text": "打开贝壳找房筛选整租", "section": ""})
    check("只有动作没有判据 => 可执行但不闭环",
          act_no_crit["actionable"] and act_no_crit["closure"] is False)

    pure_verb = lga_cli.score_item({"text": "打开", "section": ""})
    check("光一个动词不算可执行（无对象）", pure_verb["actionable"] is False)

    fresh = lga_cli.score_item({"text": "查看 2026 年新政，访问 https://example.com 下载表格", "section": ""})
    check("含链接/年份的条目被标保鲜风险", fresh["freshness_signal"] is True)

    # ---------------------------------------------------------------- 统计口径
    good = [lga_cli.score_item({"text": "打开官网注册账号，如果报错就换浏览器", "section": ""}),
            lga_cli.score_item({"text": "下载 APP 实名认证，超过3次失败就停", "section": ""})]
    s_good = lga_cli.summarize(good)
    check("两条例全闭环 => closure_rate == 1.0", s_good["closure_rate"] == 1.0, str(s_good["closure_rate"]))
    check("全闭环 => 结论 ok", s_good["verdict"] == "ok", s_good["verdict"])

    bad = [lga_cli.score_item({"text": "打开官网注册账号", "section": ""}),
           lga_cli.score_item({"text": "下载 APP 实名认证", "section": ""})]
    s_bad = lga_cli.summarize(bad)
    check("有动作无判据 => closure_rate == 0.0", s_bad["closure_rate"] == 0.0, str(s_bad["closure_rate"]))
    check("判据空洞率 == 1.0", s_bad["verdict_gap"] == 1.0, str(s_bad["verdict_gap"]))
    check("全不闭环 => 结论 caution", s_bad["verdict"] == "caution", s_bad["verdict"])

    none_actionable = [lga_cli.score_item({"text": "要注意身心健康", "section": ""})]
    s_none = lga_cli.summarize(none_actionable)
    check("一条可执行都没有 => uninformative", s_none["verdict"] == "uninformative", s_none["verdict"])

    s_empty = lga_cli.summarize([])
    check("空条目集 => degenerate", s_empty["verdict"] == "degenerate", s_empty["verdict"])
    check("空条目集不产生除零", s_empty["actionability"] == 0.0 and s_empty["closure_rate"] == 0.0)

    # 已勾选复选框是作者事记，不能占建议的分母。
    mixed_items = [
        lga_cli.score_item({"text": "- [x] 增加新版序言和声明", "checked": True, "section": ""}),
        lga_cli.score_item({"text": "- [ ] 核对房东身份证与房产证", "checked": False, "section": ""}),
    ]
    s_mix = lga_cli.summarize(mixed_items)
    check("已勾选项计入 n_meta", s_mix["n_meta"] == 1, str(s_mix["n_meta"]))
    check("已勾选项不占建议分母", s_mix["n_advice"] == 1, str(s_mix["n_advice"]))
    check("只看未勾选项 => 全部可执行", s_mix["actionability"] == 1.0, str(s_mix["actionability"]))

    # 保鲜度按文件算，不是按条目算
    s_f = lga_cli.summarize(
        [lga_cli.score_item({"text": "随便一条", "section": ""})],
        n_files=4, n_files_external=1)
    check("保鲜度 = 含外部事实的文件占比", s_f["freshness_ratio"] == 0.25, str(s_f["freshness_ratio"]))
    s_f0 = lga_cli.summarize([lga_cli.score_item({"text": "随便一条", "section": ""})])
    check("没给文件数时不除零", s_f0["freshness_ratio"] == 0.0)

    # ---------------------------------------------------------------- 退出码逐档
    check("退出码 ok/mixed/caution => 0",
          all(lga_cli.lga_exit_code({"verdict": v}) == 0 for v in ("ok", "mixed", "caution")))
    check("退出码 no_evidence/uninformative/degenerate => 2",
          all(lga_cli.lga_exit_code({"verdict": v}) == 2
              for v in ("no_evidence", "uninformative", "degenerate")))
    check("退出码未知档位 => 2（不静默放行）", lga_cli.lga_exit_code({"verdict": "huh"}) == 2)

    # 清单核真必须用自己的退出码口径，不能套 audit 的。
    # v1.0 第一版两者共用 lga_exit_code，结果"抓到 3 条错路径"静默退出 0。
    check("清单核真: suspect=0 => 0", lga_cli.list_verify_exit_code({"suspect": 0}) == 0)
    check("清单核真: suspect>0 => 2（哪怕 verdict 是 mixed）",
          lga_cli.list_verify_exit_code({"suspect": 1, "verdict": "mixed"}) == 2)
    check("两种模式的 mixed 语义相反，退出码也必须相反",
          lga_cli.lga_exit_code({"verdict": "mixed"}) == 0
          and lga_cli.list_verify_exit_code({"suspect": 1}) == 2)

    # ---------------------------------------------------------------- CLI 冒烟
    rc, out = run_cli(["audit", "--repo", "this-repo-does-not-exist-zzz-0912", "--max-files", "3"])
    check("不存在的仓库 => 退出码 2", rc == 2, f"rc={rc}")
    check("不存在的仓库报 no_evidence", "no_evidence" in out, out[:120])

    rc, out = run_cli(["list-verify", "--input", f"{HERE}/fixtures_bad.json"])
    check("错误清单 => 退出码 2", rc == 2, f"rc={rc}")
    check("错误清单被逐条点名", "not_found" in out, out[:200])

    rc, out = run_cli(["list-verify", "--input", f"{HERE}/fixtures_good.json"])
    check("正确清单 => 退出码 0", rc == 0, f"rc={rc}")

    # ---------------------------------------------------------------- 交付物对账器
    # 负向测试：注入一个错数字，对账器必须抓得住。
    # 没有这一步，对账器就会退化成「正确数字有没有出现在 HTML 里」这种永远能过的检查
    # —— 2026-09-27 我写的对账器第一版就是这么废掉的：注入 2199 它照样报"对账通过"。
    MANUAL = Path.home() / "Desktop/成果/抖音学习突破七流程-生活指南可执行性审计器-2026-09-27.html"
    if MANUAL.exists():
        with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False,
                                         encoding="utf-8") as fh:
            fh.write(MANUAL.read_text(encoding="utf-8").replace(">1693<", ">2199<", 1))
            bad_html = fh.name
        try:
            p = subprocess.run([sys.executable, f"{HERE}/audit_deliverable.py",
                                "--html", bad_html], capture_output=True, text=True, timeout=60)
            out = (p.stdout or "") + (p.stderr or "")
            check("对账器能抓到注入的错数字（负向）", p.returncode == 1, f"rc={p.returncode}")
            check("对账器报错时点名是哪张卡片的问题", "实扫条目" in out, out[:180])
        finally:
            os.unlink(bad_html)
    else:
        _lines.append("  [SKIP] 对账器负向测试：手册不在预期路径，跳过")

    # ---------------------------------------------------------------- 清单核真逻辑
    res = lga_cli.verify_list([{"name": "SurviveSJTU/SurviveSJTUManual", "star": 999999}])
    check("星数离谱 => star_mismatch（不是静默通过）",
          res["results"][0]["status"] == "star_mismatch", res["results"][0]["status"])
    res2 = lga_cli.verify_list([{"name": "", "star": None}])
    check("空条目不会崩，且被标出来", res2["results"][0]["status"] == "error")

    return report()


def report() -> int:
    print("\n".join(_lines))
    total = PASS + FAIL
    print("=" * 56)
    print(f"LGA 自检: {PASS}/{total} 通过" + ("" if FAIL == 0 else f"  —— {FAIL} 条失败"))
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
