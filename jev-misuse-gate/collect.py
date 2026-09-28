"""Jev 生态第三方语料采集（v3 —— clone 到工程内 _clones/，不再用系统 temp）。

★ v1（gh api contents + base64）产出 **1163 个 0 字节文件且全程无报错**：
   `open(local,"wb").write(base64.b64decode(...))` 是先建文件、后写内容；
   decode 一抛异常，`except: continue` 就把「建了个空壳」吞掉了 ——
   文件存在、目录看着有料、总数看着漂亮，内容全是空的，扫描结论「0 命中」纯属假象。
   ⇒ 新 iron：采集类脚本必须做过零字节自检，否则「采到了」和「采空了」长得一模一样。

★ v3 三处修正：
  1. 落地位置改成工程内 `_clones/`：系统 temp 在 Windows 下是短路径 `C:\\Users\\ADMINI~1\\...`，
     同一进程内 git clone 到那里失败，而 /tmp 下同一条命令成功。
  2. 失败打印**完整 stderr（截 400 字符）**。v2 只留第一行 "Cloning into ..."，真错被吞，白猜两轮。
  3. **不再 rmtree**：批量删除护栏会在 194 个文件时拦下并打断整个采集。clone 原地留着当底稿。
"""
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "corpus")
CLONES = os.path.join(HERE, "_clones")
REPOS = [
    "shitianfang/jev-use",
    "blakestone-x/jev-mcp",
    "PyModel/jev-judge-mcp",
    "Brainwires/jevwire",
    "Mawfyy/jevflow",
    "abhixhek/jevcal",
    "simota/tenbin",
    "legacybridge-tech/pi-typesafe-jev",
]
KEEP_EXT = {".py", ".ts", ".js", ".mjs", ".json", ".md", ".sh", ".yaml", ".yml"}
MAX_MB = 2          # 单个文件超过这个就跳过（minified bundle / lockfile）
SKIP_DIR = {"node_modules", ".git", "dist", ".venv", "venv", "__pycache__"}


def clone_and_copy(repo: str) -> int:
    clone_dir = os.path.join(CLONES, repo.replace("/", "__"))
    os.makedirs(clone_dir, exist_ok=True)
    last = ""
    for attempt in (1, 2):
        r = subprocess.run(["git", "clone", "--depth", "1",
                            f"https://github.com/{repo}", clone_dir],
                           capture_output=True, text=True, timeout=180)
        if r.returncode == 0 and os.path.isdir(os.path.join(clone_dir, ".git")):
            break
        last = f"（第 {attempt} 次）rc={r.returncode} stderr={r.stderr.strip()[:400]}"
        if attempt == 1:
            print(f"  ↻ {repo} 首次失败，重试一次…", flush=True)
            shutil.rmtree(clone_dir, ignore_errors=True)
            os.makedirs(clone_dir, exist_ok=True)
    else:
        print(f"[skip] {repo} —— clone 失败: {last}", flush=True)
        return -1

    kept = 0
    for dirpath, dirnames, files in os.walk(clone_dir):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIR]
        for fn in files:
            if not fn.endswith(tuple(KEEP_EXT)):
                continue
            src = os.path.join(dirpath, fn)
            try:
                if os.path.getsize(src) > MAX_MB * 1024 * 1024:
                    continue
                body = open(src, "rb").read()          # ★ v1 的坑：先建文件后写内容 ⇒ 0 字节空壳
            except OSError:
                continue
            if not body:                                # ★ 空文件根本不落盘
                continue
            rel = os.path.relpath(src, clone_dir).replace(os.sep, "__")
            dst = os.path.join(OUT, repo.replace("/", "__") + "__" + rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            with open(dst, "wb") as f:
                f.write(body)
            kept += 1
    print(f"[ok] {repo} → {kept} 个文件", flush=True)
    return kept


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    total = 0
    for repo in REPOS:
        total += max(0, clone_and_copy(repo))

    # ★ 过零字节自检：采集类脚本的兜底闸门。
    all_files, empties = [], []
    for dp, _d, fns in os.walk(OUT):
        for fn in fns:
            p = os.path.join(dp, fn)
            all_files.append(p)
            if os.path.getsize(p) == 0:
                empties.append(p)
    print(f"\n合计落盘 {len(all_files)} 文件（0 字节 {len(empties)} 个）→ {OUT}")
    if empties:
        print(f"[FATAL] 存在 0 字节文件，采集不可信 —— 先修再往下走")
        return 1
    if total == 0:
        print("[FATAL] 一个文件都没采到 —— 视为采集失败，不允许据此下任何结论")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
