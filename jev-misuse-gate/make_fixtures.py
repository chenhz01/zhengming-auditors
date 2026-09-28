"""生成 8 个 fixture，对应 jvg_cli.py 里的 FIXTURE_EXPECT。

★ f07/f08 是**位置判据的探针**，不是语料形态：
    f07 的 rm -rf 在上一个函数里、距调用点 13 行（> CONTEXT_LINES=12）⇒ 不算同一个上下文 ⇒ []
    f08 的 rm -rf 在**同一个函数开头**、距调用点 19 行（也 > CONTEXT_LINES）⇒ 同样不算 ⇒ []

  ★ f08 第一版是**假绿**：当时 IRREVERSIBLE_RE 匹配不到 `['rm', '-rf']` 的引号形态，
    所以哪怕窗口因文件太短已覆盖全文、rm -rf 明明在窗口内，也判不出 —— 两个探针互相掩护。
    修好词表后 f08 立刻翻正，所以 f08 必须重新设计成「距离真的超出窗口」，
    并在 main() 里**断言距离**，否则探针会退化成一个撞运气的样子。
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jvg_cli import CONTEXT_LINES  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
GAP = 16  # f08 里 rm -rf 与调用点之间要塞多少行无关逻辑


def w(name: str, body: str) -> None:
    open(os.path.join(OUT, name), "w", encoding="utf-8").write(
        "# f-%s\n" % name.split("_")[1].rstrip("_0123456789") + body)


def call(extra: str = "") -> str:
    return "    resp = client.system_one(state=state, questions=questions)  # Jev call%s\n" % extra


def f01_math() -> None:
    w("f01_math.py", "\n".join([
        "def invoice_check(doc):",
        "    total = sum(l.amount for l in doc.lines)",
        "    assert abs(total - doc.invoice_total) < 0.01",
        call(),
        "    return resp.answers['match']",
        ""]))


def f02_clean() -> None:
    w("f02_clean.py", "\n".join([
        "def tag_of(row):",
        "    q = Choice(instructions='route this row', criteria=ROUTES)",
        call(),
        "    return resp.answers['route']",
        ""]))


def f03_chinese() -> None:
    w("f03_chinese.py", "\n".join([
        "def classify_cn(msg):",
        "    state = {'customer_message': msg}",
        "    q = Choice(instructions='判断 customer_message 属于哪一类客户消息')",
        call(),
        "    return resp.answers['kind']",
        ""]))


def f04_irreversible() -> None:
    w("f04_irreversible.py", "\n".join([
        "def refund(path):",
        "    if confirm(path):",
        "        subprocess.run(['rm', '-rf', path])",
        "    q = Choice(instructions='should we refund', criteria=YESNO)",
        call(),
        "    return resp.answers['ok']",
        ""]))


def f05_coarse() -> None:
    w("f05_coarse.py", "\n".join([
        "def score_doc(page_text):",
        "    q = Score(instructions='grade this')",
        call(),
        "    return resp.answers['grade']",
        ""]))


def f06_multizone() -> None:
    w("f06_multizone.py", "\n".join([
        "def settle_money(rec):",
        "    total = sum(rec.amounts)",
        "    subprocess.run(['rm', '-rf', rec.path])",
        "    q = Choice(instructions='finalize', criteria=OUT)",
        call(),
        "    return resp.answers['x']",
        ""]))


def f07_context() -> None:
    # ★ rm -rf 在**上一个函数**里、调用点在该函数深处，两者相距 18 行 > CONTEXT_LINES。
    #   第一版相距正好 12 行（= CONTEXT_LINES），窗口 lo 恰好切到 rm 那一行 ⇒ 判定会翻正；
    #   之前显示 OK 纯粹因为引号形态让词表零命中 —— 探针与判据互相掩护，见 assert_position_probes()。
    #   ★ 注释一律英文：否则这个「位置探针」会同时踩到 chinese 档，一次钉不住两个判据。
    pad = ["    # unrelated step %d, no keyword here" % i for i in range(GAP)]
    w("f07_context.py", "\n".join([
        "def cleanup(path):",
        "    subprocess.run(['rm', '-rf', path])",
    ] + pad + [
        "def decide(row):",
        "    q = Choice(instructions='pick bucket', criteria=BUCKETS)",
        call(),
        "    return resp.answers['b']",
        ""]))


def f08_distant() -> None:
    # ★ 注释一律写英文：一旦混入中文任务词，这个「位置探针」会同时踩到 chinese 档，
    #   探针就不再只测一件事了（§S3.5 第 2 条：一次只钉一个判据）。
    pad = ["    # unrelated step %d, no keyword here" % i for i in range(GAP)]
    w("f08_distant.py", "\n".join([
        "def flush_all(jobs):",
        "    subprocess.run(['rm', '-rf', jobs.tmp])",
    ] + pad + [
        "    q = Choice(instructions='pick bucket', criteria=BUCKETS)",
        call(),
        "    return resp.answers['b']",
        ""]))


def assert_position_probes() -> None:
    """位置探针的距离必须当场断言，否则「探针」只是长得像探针。"""
    for name in ("f07_context.py", "f08_distant.py"):
        path = os.path.join(OUT, name)
        lines = open(path, encoding="utf-8").read().splitlines()
        ri = next((i for i, l in enumerate(lines)
                   if re.search(r"\brm[^\w\n]*-rf\b", l, re.IGNORECASE)), None)
        ci = next((i for i, l in enumerate(lines)
                   if "client.system_one" in l), None)
        assert ri is not None and ci is not None, f"{name}: 没找到 rm -rf 或调用点"
        dist = abs(ri - ci)
        assert dist > CONTEXT_LINES, (
            f"{name}: rm -rf(行{ri+1}) 与调用点(行{ci+1}) 相距 {dist} 行，"
            f"未超过 CONTEXT_LINES={CONTEXT_LINES} —— 这个探针已经不测位置了")
        print(f"  · {name}: rm -rf 行{ri+1} ↔ 调用点 行{ci+1}，相距 {dist} 行 > {CONTEXT_LINES} ✓")


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    for fn in (f01_math, f02_clean, f03_chinese, f04_irreversible,
               f05_coarse, f06_multizone, f07_context, f08_distant):
        fn()
    print(f"[done] 8 个 fixture → {OUT}")
    print("位置探针距离自检：")
    assert_position_probes()


if __name__ == "__main__":
    main()
