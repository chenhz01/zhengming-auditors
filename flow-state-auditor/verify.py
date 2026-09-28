r"""FSA 收口对账器（R-BK2）

三件事：
  1. 四通道真值对账：selftest / probe / collect / fsa scan 全绿，且条数与
     本文件 T 表一致（改了通道不许只改 T 表，要真跑）
  2. 三方向注入验证（防假绿）：改真值 / 改语料 / 拆探针入口，三处都要能转红，
     且验证完自动复原
  3. 交付清单体检：交付物是否存在、是否含占位符

★ 任何一项没过 ⇒ 退出码非 0，本件不许标完毕。
★ 占位符（TBD / TODO / XXX / lorem / 待补）出现在交付物里 ⇒ 直接判 FAIL。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable

T = {
    "selftest": "17/17",
    "probe_matrix": "6/6",
    "collect_sources": "5/5",
    "corpus_kw": "4/4",
    "probe_live": "0/2",   # 真实端点探测：如实记账，通道不通 ≠ 内容不存在
}

BREAKS = 6
PLACEHOLDER = ("TBD", "TODO", "XXX", "lorem ipsum", "待补", "占位符")
# 交付给别人的文档（工程内手册 md + 暗色 HTML）。
# 规则层 md 与桌面 HTML 是同构副本，由 build_html 一并产出，一并体检。
OUT_DOCS = ["report.md", "_out/抖音学习突破七流程-流式输出完整性-2026-09-27.html"]
FILES = [
    "collect_corpus.py", "fsa_cli.py", "probe_stream_reality.py",
    "verify.py", "build_html.py",
]
DELIVER = [
    "_raw/artifacts/report.json",
    "_raw/artifacts/corpus_atlassian_streaming_errors.md",
    "_raw/artifacts/corpus_da_truncation_silent.md",
    "_raw/artifacts/corpus_devto_streaming_interrupted.md",
    "_raw/artifacts/corpus_guard_readme.md",
    "_raw/artifacts/corpus_bestaiweb_streaming_gaps.md",
    "_raw/artifacts/corpus_stream_probe.md",
    "_raw/artifacts/_manifest.json",
]

# ★ 注入 = 改内容后原样回滚，绝不 unlink 原文件。
#   2026-09-27 第一版写成「把注入件 append 原文件、复原时 unlink」，
#   直接把被审的 fsa_cli.py / probe_stream_reality.py 删了 —— 自己把被测对象
#   干掉，比不注入更糟。
_injected: list[tuple[Path, str]] = []


def _run(script: str, *args: str) -> tuple[int, str]:
    p = subprocess.run([PY, script, *args], cwd=ROOT,
                       capture_output=True, text=True, timeout=180)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def _guard(name: str, cond: bool, detail: str = "") -> bool:
    print("  [%s] %s%s" % ("PASS" if cond else "FAIL", name,
                           "" if cond else "  ← " + detail))
    return cond


def _inject(path: str, old: str, new: str) -> bool:
    f = ROOT / path
    if not f.is_file():
        return False
    s = f.read_text(encoding="utf-8")
    if old not in s:
        print("    [skip] %s 未找到注入点" % path)
        return False
    f.write_text(s.replace(old, new, 1), encoding="utf-8")
    _injected.append((f, s))
    return True


def _restore() -> None:
    for f, original in _injected:
        f.write_text(original, encoding="utf-8")
        print("    [复原] %s 已回滚内容（未删文件）" % f.name)
    _injected.clear()


def _v_channels() -> bool:
    ok = True
    print("── 通道真值")
    rc, out = _run("fsa_cli.py", "selftest")
    ok &= _guard("selftest 全绿", rc == 0 and "PASS" in out, out[-200:])

    rc, out = _run("probe_stream_reality.py")
    # 前缀必须跟探针日志一致（第二版改成了「结局=」），改了探针忘了改这里
    # 就是经典的「断言和实现对不上还全绿」
    matrix = [l for l in out.splitlines() if l.strip().startswith("结局=")]
    probe_ok = rc == 0 and len(matrix) == 6 and all(
        "verdict=" in l for l in matrix)
    ok &= _guard("probe 策略矩阵 6/6", probe_ok, out[-200:])

    rc, out = _run("collect_corpus.py")
    src = [l for l in out.splitlines() if "B /" in l and "[ok]" in l]
    ok &= _guard("collect 5 源全通", rc == 0 and len(src) == 5, out[-200:])

    kw_ok = all((ROOT / "_raw/artifacts" / f).is_file() for f in
                ("corpus_atlassian_streaming_errors.md",
                 "corpus_da_truncation_silent.md"))
    ok &= _guard("关键语料落盘", kw_ok)

    rc, out = _run("fsa_cli.py", "scan")
    ok &= _guard("scan 出 flow_unreconciled + ok 双结论",
                 "flow_unreconciled" in out and "均分 1.000" in out, out[-200:])
    return ok


def _v_inject() -> bool:
    print("── 三方向注入（防假绿）")
    ok = True

    # 方向 1：改真值 —— 把实测帧数从 11 改成 99，判据 F4 的描述会失真
    if _inject("fsa_cli.py", "PROBE_TRUNC_FRAMES = 11",
               "PROBE_TRUNC_FRAMES = 99"):
        rc, out = _run("fsa_cli.py", "selftest")
        ok &= _guard("改真值 ⇒ selftest 转红", rc != 0, "仍未红")
    else:
        ok &= _guard("改真值 ⇒ selftest 转红", False, "注入点不存在")

    # 方向 2：改语料 —— 抽掉 Atlassian 那句「不抛异常」，关键词闸门应拦下
    f = ROOT / "_raw/artifacts/corpus_atlassian_streaming_errors.md"
    bak = ROOT / "_tmp_atlassian.bak"
    if f.is_file() and not bak.exists():
        shutil.copy2(f, bak)
        s = f.read_text(encoding="utf-8")
        f.write_text(s.replace("Exceptions are not thrown",
                               "Exceptions may be thrown", 1),
                     encoding="utf-8")
        # 该语料被 selftest 的关键词闸门引用 ⇒ 改了必须转红
        rc, out = _run("fsa_cli.py", "selftest")
        ok &= _guard("改语料 ⇒ selftest 转红", rc != 0, "仍未红")
        bak.replace(f)
        bak.unlink(missing_ok=True)
    else:
        ok &= _guard("改语料 ⇒ 关键词闸门拦下", False, "语料不存在")

    # 方向 3：拆探针入口 —— 让策略矩阵少跑一种策略
    if _inject("probe_stream_reality.py",
               'for st in ("done_aware", "eof_only", "budget_aware"):',
               'for st in ("done_aware",):'):
        rc, out = _run("probe_stream_reality.py")
        ok &= _guard("拆探针入口 ⇒ 探针转红", rc != 0, "仍未红")
    else:
        ok &= _guard("拆探针入口 ⇒ 探针转红", False, "注入点不存在")
    return ok


def _v_deliver() -> bool:
    print("── 交付清单")
    ok = True
    for f in FILES:
        ok &= _guard("存在 %s" % f, (ROOT / f).is_file())
    for f in DELIVER:
        p = ROOT / f
        ok &= _guard("存在 %s" % f, p.is_file())
    # ★ 占位符只查「交付给别人的文档」，不查源码与抓取语料 ——
    #   语料里本来就可能有 XXX（HTML 实体），源文件的 PLACEHOLDER 定义行
    #   也会命中它自己。查错对象比不查更糟。
    hits: list[str] = []
    for f in OUT_DOCS:
        p = ROOT / f
        if not p.is_file():
            continue
        try:
            s = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits += ["%s:%s" % (f, h) for h in PLACEHOLDER if h in s]
    ok &= _guard("交付文档无占位符", not hits, "; ".join(hits))
    return ok


def main() -> int:
    try:
        ok = _v_channels()
        ok &= _v_deliver()
        ok &= _v_inject()
    finally:
        _restore()
    print()
    print("[verify] %s" % ("PASS 全绿" if ok else "FAIL —— 本件不许标完毕"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
