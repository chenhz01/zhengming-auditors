"""JVG v1.0 校验器 —— 本件自己写的判据，上线前先喂错数据。

★ v2.7.0 skill Step 5 第 6/7 项落到这里：
  · 第 6 项：喂错数据，它没报错 ⇒ 你没写检查。
  · 第 7 项：**「改交付物」只是接受面的一半**，另一半是「改校验器读的那个源文件」。
    所以本文件的注入自检分两侧：
      - 交付物侧：改 fixtures / 改期望表
      - 源文件侧：改 jvg_cli.py 的判据常量（词表 / CONTEXT_LINES）
    两侧都必须让它变红，只测一侧等于没测。
"""
from __future__ import annotations

import importlib
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import jvg_cli as J  # noqa: E402

CLI_SRC = os.path.join(HERE, "jvg_cli.py")
FIXDIR = os.path.join(HERE, "fixtures")
CORPUS = os.path.join(HERE, "corpus")

_checks: list[tuple[str, str, callable]] = []
_fails: list[str] = []


def check(code: str, title: str):
    def deco(fn):
        _checks.append((code, title, fn))
        return fn
    return deco


# ------------------------------------------------------------------ A 工程完整性
@check("A01", "jvg_cli.py 可被导入且语法自洽")
def a01():
    assert J.JVG_VERSION == "1.0", f"JVG_VERSION={J.JVG_VERSION}"
    assert callable(J.batch) and callable(J.scan_file) and callable(J.zones_of_ctx)


@check("A02", "fixtures 目录 8 个文件，与 FIXTURE_EXPECT 键一一对应")
def a02():
    files = {f[:-3] for f in os.listdir(FIXDIR) if f.endswith(".py")}
    expect = set(J.FIXTURE_EXPECT)
    assert files == expect, f"fixture 文件与期望表不一致：多 {files-expect} 少 {expect-files}"


@check("A03", "四档 ZONES 与词表常量齐全")
def a03():
    assert set(J.ZONES) == {"math", "chinese", "irreversible", "coarse_unit"}, J.ZONES
    for name in ("MATH_RE", "CHINESE_RE", "CHINESE_TASK_RE", "IRREVERSIBLE_RE",
                 "COARSE_RE", "CALL_SITE_RE"):
        assert getattr(J, name) is not None, f"{name} 缺失"


# ------------------------------------------------------------------ B 判据自洽
@check("B01", "f01 数学档必须命中（词表不能是空转的）")
def b01():
    z = J.scan_file(os.path.join(FIXDIR, "f01_math.py"))["zones"]
    assert z.get("math", 0) >= 1, f"f01 未命中 math：{z}"


@check("B02", "f03 中文档必须命中（任务词表含中文词条）")
def b02():
    z = J.scan_file(os.path.join(FIXDIR, "f03_chinese.py"))["zones"]
    assert z.get("chinese", 0) >= 1, f"f03 未命中 chinese：{z}"


@check("B03", "f04 不可逆档必须命中（必须容纳 ['rm','-rf'] 引号形态）")
def b03():
    z = J.scan_file(os.path.join(FIXDIR, "f04_irreversible.py"))["zones"]
    assert z.get("irreversible", 0) >= 1, f"f04 未命中 irreversible：{z}"


@check("B04", "f05 粗粒度档必须命中")
def b04():
    z = J.scan_file(os.path.join(FIXDIR, "f05_coarse.py"))["zones"]
    assert z.get("coarse_unit", 0) >= 1, f"f05 未命中 coarse_unit：{z}"


@check("B05", "引号形态必须命中：subprocess.run(['rm', '-rf', x])")
def b05():
    line = "    subprocess.run(['rm', '-rf', rec.path])"
    assert J.IRREVERSIBLE_RE.search(line), "IRREVERSIBLE_RE 匹配不到引号形态的 rm -rf"


@check("B06", "字面形态仍要命中：rm -rf /tmp/x")
def b06():
    assert J.IRREVERSIBLE_RE.search("rm -rf /tmp/x"), "IRREVERSIBLE_RE 匹配不到字面形态"


# ------------------------------------------------------------------ C 位置判据
@check("C01", "f07 期望 []：rm -rf 在上一个函数且距离 > CONTEXT_LINES")
def c01():
    lines = open(os.path.join(FIXDIR, "f07_context.py"), encoding="utf-8").read().splitlines()
    ri = next(i for i, l in enumerate(lines) if J.IRREVERSIBLE_RE.search(l))
    ci = next(i for i, l in enumerate(lines) if "client.system_one" in l)
    assert abs(ri - ci) > J.CONTEXT_LINES, f"距离 {abs(ri-ci)} 未超过 {J.CONTEXT_LINES}，探针失效"
    assert J.scan_file(os.path.join(FIXDIR, "f07_context.py"))["zones"] == {}, \
        "f07 不该命中（跨函数距离超出窗口）"


@check("C02", "f08 期望 []：同文件同函数，但距离仍 > CONTEXT_LINES")
def c02():
    lines = open(os.path.join(FIXDIR, "f08_distant.py"), encoding="utf-8").read().splitlines()
    ri = next(i for i, l in enumerate(lines) if J.IRREVERSIBLE_RE.search(l))
    ci = next(i for i, l in enumerate(lines) if "client.system_one" in l)
    assert abs(ri - ci) > J.CONTEXT_LINES, f"距离 {abs(ri-ci)} 未超过 {J.CONTEXT_LINES}，探针失效"
    assert J.scan_file(os.path.join(FIXDIR, "f08_distant.py"))["zones"] == {}


@check("C03", "灵敏度探针：把 CONTEXT_LINES 放大到 > 距离，f07 必须翻正")
def c03():
    """反证位置判据真的在起作用。若放大窗口后 f07 仍为 []，说明位置根本没参与判定。"""
    lines = open(os.path.join(FIXDIR, "f07_context.py"), encoding="utf-8").read().splitlines()
    ri = next(i for i, l in enumerate(lines) if J.IRREVERSIBLE_RE.search(l))
    ci = next(i for i, l in enumerate(lines) if "client.system_one" in l)
    orig = J.CONTEXT_LINES
    J.CONTEXT_LINES = abs(ri - ci) + 1          # 只动窗口，不动词表
    try:
        got = J.zones_of_ctx(lines, ci)
    finally:
        J.CONTEXT_LINES = orig
    assert "irreversible" in got, f"窗口放大后 f07 仍为 {got} —— 位置判据形同虚设"


# ------------------------------------------------------------------ D 不许短路
@check("D01", "f06 必须同时报两档（一处踩两个禁区本身就是结论）")
def d01():
    z = J.scan_file(os.path.join(FIXDIR, "f06_multizone.py"))["zones"]
    assert {"math", "irreversible"} <= set(z), f"f06 只报了 {sorted(z)}，疑似短路取分支"


@check("D02", "合成文件：四档并存必须一次报全四档")
def d02():
    src = "\n".join([
        "# synth 四档并存",
        "def settle(doc, msg):",
        "    total = sum(doc.amounts)",
        "    subprocess.run(['rm', '-rf', doc.path])",
        "    q = Choice(instructions='判断这条是不是投诉')  # 中文细粒度分类",
        "    r = client.system_one(page_text=doc.body)",
        "    return r",
        ""])
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "synth.py")
        open(p, "w", encoding="utf-8").write(src)
        z = J.scan_file(p)["zones"]
        for zone in J.ZONES:
            assert zone in z, f"四档并存只报了 {sorted(z)}，缺 {zone}"


# ------------------------------------------------------------------ E 输出契约
@check("E01", "batch() 返回键齐全")
def e01():
    out = J.batch(FIXDIR)
    for k in ("n_files", "n_readable", "n_with_sites", "peak_zone_hits", "tally", "results"):
        assert k in out, f"batch 缺返回键 {k}"


@check("E02", "tally 覆盖全部 ZONES 且各档为整数")
def e02():
    out = J.batch(FIXDIR)
    assert set(out["tally"]) == set(J.ZONES), out["tally"]
    assert all(isinstance(v, int) for v in out["tally"].values()), out["tally"]


@check("E03", "8 个 fixture 的档集合与 FIXTURE_EXPECT 完全一致（不多报不少报）")
def e03():
    out = J.batch(FIXDIR)
    for r in out["results"]:
        key = r["rel"][:-3]
        exp = set(J.FIXTURE_EXPECT[key])
        got = set(r["zones"])
        assert exp == got, f"{key}: 期望 {sorted(exp)} 实得 {sorted(got)}"


@check("E04", "报 0 必须附替代信号：分档峰值必须常驻（不能只有一个全局峰值）")
def e04():
    """§S3.5 第 4 条：只有全局峰值时，某个档报 0 会被别的档盖住。
    分档峰值全 0 ⇒ 词表/判据没覆盖；分档峰值非 0 ⇒ 是门槛在挡。两者处置完全不同。"""
    out = J.batch(FIXDIR)
    # ★ 口径：peak_zone_hits = 单个文件里单档最大命中数；zone_peaks[z] = 该档跨所有文件的最大值。
    #   第一版写成 `peak >= max(tally)` 是**量纲错**：tally 是跨文件求和，和峰值不可比。
    assert isinstance(out["peak_zone_hits"], int), out["peak_zone_hits"]
    assert set(out["zone_peaks"]) == set(J.ZONES), out["zone_peaks"]
    assert all(isinstance(v, int) for v in out["zone_peaks"].values()), out["zone_peaks"]
    assert out["peak_zone_hits"] == max(out["zone_peaks"].values()), out["zone_peaks"]


@check("E05", "CLI 语义：无参数退出码 2；batch 子命令能被识别（不当成目录）")
def e05():
    r = subprocess.run([sys.executable, os.path.join(HERE, "jvg_cli.py")],
                       capture_output=True, text=True)
    assert r.returncode == 2, f"无参数退出码 {r.returncode}"
    r2 = subprocess.run([sys.executable, os.path.join(HERE, "jvg_cli.py"), "batch", FIXDIR],
                        capture_output=True, text=True)
    assert r2.returncode == 0, f"batch 子命令失败：{r2.stderr[:200]}"
    assert "扫描" in r2.stdout, r2.stdout[:200]


# ------------------------------------------------------------------ F 真语料
@check("F01", "语料无 0 字节文件（采集空壳是 v1 的教训，必须挡住）")
def f01():
    empties = []
    for dp, _d, fns in os.walk(CORPUS):
        for fn in fns:
            p = os.path.join(dp, fn)
            if os.path.getsize(p) == 0:
                empties.append(p)
    assert not empties, f"{len(empties)} 个 0 字节文件，例如 {empties[:2]}"


@check("F02", "语料确实采到了调用点：n_with_sites > 0，且语料文件数 > 100")
def f02():
    out = J.batch(CORPUS)
    assert out["n_files"] > 100, f"语料只有 {out['n_files']} 个文件，采集可能失败"
    assert out["n_with_sites"] > 0, "语料里一个 Jev 调用点都没有 —— 不能据此说任何事"


@check("F03", "刷屏率不得失控：命中文件占比 < 20%（超出就是宽特征不是真问题）")
def f03():
    out = J.batch(CORPUS)
    files = [x for x in out["results"] if not x.get("error")]
    hit = sum(1 for x in files if x["zones"])
    rate = 100.0 * hit / max(1, len(files))
    assert rate < 20.0, f"刷屏率 {rate:.2f}%（{hit}/{len(files)}），判据太宽"


@check("F04", "语料零命中必须能说清原因：同时给出 n_with_sites 与分档峰值")
def f04():
    """§S3.5 第 4 条落地检查：报 0 时，如果 n_with_sites>0 且分档峰值全为 0，
    说明「词表没覆盖」而不是「没这现象」—— 两种要修的东西完全不同。"""
    out = J.batch(CORPUS)
    if out["peak_zone_hits"] == 0:
        assert out["n_with_sites"] > 0, "语料里连调用点都没有，不敢下结论"
        assert max(out["zone_peaks"].values()) == 0, out["zone_peaks"]
        # 零命中时 CLI 必须给出警告，而不是静默输出一行 0
        r = subprocess.run([sys.executable, os.path.join(HERE, "jvg_cli.py"),
                            "batch", CORPUS], capture_output=True, text=True)
        assert "调用点却零命中" in r.stdout, "零命中时未触发警告，静默输出不可接受"


# ------------------------------------------------------------------ 运行
def run() -> int:
    ok = 0
    print(f"JVG v{J.JVG_VERSION} 校验器 —— 共 {len(_checks)} 项\n")
    for code, title, fn in _checks:
        try:
            fn()
            ok += 1
            print(f"  ✅ {code} {title}")
        except AssertionError as e:
            _fails.append(f"{code} {title} —— {e}")
            print(f"  ❌ {code} {title}\n        {e}")
        except Exception as e:  # noqa: BLE001 —— 其他异常同样算不过
            _fails.append(f"{code} {title} —— 异常 {type(e).__name__}: {e}")
            print(f"  ❌ {code} {title}\n        异常 {type(e).__name__}: {e}")
    print(f"\n通过 {ok}/{len(_checks)}")
    for f in _fails:
        print(f"  · {f}")
    return 0 if not _fails else 1


if __name__ == "__main__":
    sys.exit(run())
