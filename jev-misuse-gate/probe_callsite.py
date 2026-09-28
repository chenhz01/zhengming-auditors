"""一次性探针：Jev 生态里「什么才算一次真调用」。

不猜，把每种候选标识符的**真实出现形态**打出来看。结论要写回 jvg_cli.py 的 CALL_SITE_RE。
"""
import collections
import os
import re

PATS = {
    "v1/systemone": r"/v1/systemone",
    "system_one(": r"system_one\s*\(",
    "systemOne(": r"systemOne\s*\(",
    "TypeSafeBackend": r"TypeSafeBackend",
    "TypeSafeClassifier": r"TypeSafeClassifier",
    "Classifier(": r"Classifier\s*\(",
    "typesafe.ai": r"typesafe\.ai",
    "TYPESAFE_API_KEY": r"TYPESAFE_API_KEY",
    "api.typesafe.ai": r"api\.typesafe\.ai",
}


def main() -> None:
    counts = collections.Counter()
    samples = collections.defaultdict(list)
    for dp, _d, fns in os.walk("corpus"):
        for fn in fns:
            if not fn.endswith((".py", ".ts", ".mjs", ".js")):
                continue
            path = os.path.join(dp, fn)
            rel = path.split("corpus" + os.sep)[-1]
            for i, line in enumerate(open(path, encoding="utf-8", errors="replace").read().splitlines()):
                for k, pt in PATS.items():
                    if re.search(pt, line, re.IGNORECASE):
                        counts[k] += 1
                        if len(samples[k]) < 5:
                            samples[k].append((rel[-60:], i + 1, line.strip()[:105]))
    for k in PATS:
        print(f"{k:<20} {counts[k]:>5} 处")
        for rel, ln, txt in samples[k]:
            print(f"     {rel}:{ln} | {txt}")
        print()


if __name__ == "__main__":
    main()
