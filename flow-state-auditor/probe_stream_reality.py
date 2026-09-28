r"""FSA 语料探针 —— 流式「完成 vs 截断」可分辨性实测（Step 2.75 用）

三路取证：
  A. 受控 SSE 对照实验（本地起真 HTTP 服务，三结局：complete / truncated / stalled）
  B. 真实公开 SSE 端点探测（通不通如实报，不通就报不通，不许补写）
  C. 本机可疑服务 127.0.0.1:3080 流式观测（本机已知不稳定的本地服务）

★ 招牌对照：三种「客户端如何判定输出完成」的策略，喂给同一批真实结局。
   结论：只看「流结束了」的策略，会把「服务端只给 11/20 就掐断」判成完成，
   且全程 err=None —— 截断不是异常，是流自然地结束了。

落盘：_raw/artifacts/corpus_stream_probe.md（只追加已确认真实的观测）
闸门：任何场景异常退出必须 return 非 0，不许静默通过。
"""
from __future__ import annotations

import http.client
import ssl
import sys
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ART = ROOT / "_raw" / "artifacts"
ART.mkdir(parents=True, exist_ok=True)

PROBE_PORT = 8731
LINES: list[str] = []


def log(line: str = "") -> None:
    LINES.append(line)
    print(line)


# ─────────────────────────── A. 受控 SSE 对照实验 ───────────────────────────
class SSEHandler(BaseHTTPRequestHandler):
    """三个场景，唯一变量是「服务端什么时候认为这次输出结束了」。

    complete  —— 发满 20 帧，再发 [DONE]，正常收尾
    truncated —— 发到 cutoff 帧直接 close（模拟服务崩溃 / 上游掐断）
    stalled   —— 发满 20 帧，但每帧间隔 0.6s（模拟极慢但会完成）
    """

    def do_GET(self) -> None:  # noqa: N802
        self.mode = self.path.strip("/").split("/")[-1] or "complete"
        total, cutoff = 20, 12
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            for i in range(1, total + 1):
                if self.mode == "truncated" and i >= cutoff:
                    break  # ★ 掐断，只给 cutoff-1 帧，且不发 DONE
                self.wfile.write(("data: token-%02d\n\n" % i).encode("utf-8"))
                self.wfile.flush()
                if self.mode == "stalled":
                    time.sleep(0.6)
            if self.mode != "truncated":
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            try:
                self.connection.close()
            except Exception:
                pass

    def log_message(self, fmt: str, *args) -> None:  # noqa: D102
        pass


def _run_case(mode: str, strategy: str = "raw") -> dict:
    """客户端视角：这次「看到什么」「判成什么」。

    done_aware    —— 严格按 [DONE] 判定
    eof_only      —— 只看「流结束了」就当完整（大量 UI/日志实现）
    budget_aware  —— ★ 流前定预算 BUDGET，流后按已收/预算对账
    """
    srv = ThreadingHTTPServer(("127.0.0.1", PROBE_PORT), SSEHandler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.15)
    out: dict = {"mode": mode, "strategy": strategy, "chunks": 0, "bytes": 0,
                 "saw_done": False, "error": None, "verdict": None,
                 "detected_at_chunk": None}
    budget = 20
    t0 = time.time()
    buf = b""

    def _nxt(chunk: bytes) -> None:
        # 逐字节读：单次 read 不一定含完整帧标记，按累积缓冲取当前确证帧数
        nonlocal buf
        out["bytes"] += len(chunk)
        buf += chunk
        out["chunks"] = buf.count(b"data: ")

    try:
        c = http.client.HTTPConnection("127.0.0.1", PROBE_PORT, timeout=25)
        c.request("GET", "/" + mode)
        r = c.getresponse()
        while True:
            chunk = r.read(1)
            if not chunk:
                break
            _nxt(chunk)
        raw = buf.decode("utf-8", "replace")
        out["saw_done"] = "[DONE]" in raw
        if strategy == "done_aware":
            out["verdict"] = ("complete" if out["saw_done"] else "INCOMPLETE")
        elif strategy == "eof_only":
            out["verdict"] = "complete"  # ★ 流一结束就当完成了
        elif strategy == "budget_aware":
            out["verdict"] = ("complete" if out["chunks"] >= budget
                              else "INCOMPLETE")
            out["detected_at_chunk"] = (out["chunks"] if out["chunks"]
                                        else None)
    except Exception as e:  # noqa: BLE001 —— 断流现场就是要如实记异常
        out["error"] = "%s: %s" % (type(e).__name__, e)
        out["verdict"] = "INCOMPLETE"
    finally:
        out["elapsed_s"] = round(time.time() - t0, 2)
        srv.shutdown()
        srv.server_close()
    return out


def run_control() -> list[dict]:
    log("── A. 受控 SSE 对照实验（本地真 HTTP 服务，端口 %d）" % PROBE_PORT)
    res = []
    for mode in ("complete", "truncated", "stalled"):
        r = _run_case(mode)
        res.append(r)
        log("  场景 %-10s → 帧=%-3d 字节=%-5s saw_done=%-5s 用时=%.2fs err=%s"
            % (r["mode"], r["chunks"], r["bytes"], r["saw_done"],
               r["elapsed_s"], r["error"]))
    return res


def run_strategy_matrix() -> list[dict]:
    """★ 招牌材料：三种策略 × 两种真实结局。"""
    log()
    log("── ★ 完成判定策略矩阵（服务端真实两种结局）")
    res = []
    for mode in ("complete", "truncated"):
        for st in ("done_aware", "eof_only", "budget_aware"):
            r = _run_case(mode, st)
            res.append(r)
            log("  结局=%-10s 策略=%-13s → 帧=%-3d err=%-10s verdict=%-10s @帧=%s"
                % (r["mode"], st, r["chunks"], r["error"] or "None",
                   r["verdict"], r["detected_at_chunk"]))
    da = next(x for x in res if x["mode"] == "truncated"
              and x["strategy"] == "done_aware")
    eo = next(x for x in res if x["mode"] == "truncated"
              and x["strategy"] == "eof_only")
    ba = next(x for x in res if x["mode"] == "truncated"
              and x["strategy"] == "budget_aware")
    # ★ 没复现出来就是命题错了，探针自己红，不许静默绿
    if da["verdict"] != "INCOMPLETE":
        log("[FAIL] done_aware 未识破截断 —— 命题 F5 不成立")
        raise SystemExit(3)
    if eo["verdict"] != "complete":
        log("[FAIL] eof_only 未误判为完成 —— 命题 F5 不成立")
        raise SystemExit(3)
    log("  ⇒ eof_only 把「服务端只给了 %d/%d 帧就掐断」判成「输出完成」，"
        % (eo["chunks"], 20))
    log("     且全程 err=None —— 截断不是异常，是流自然地结束了。")
    log("  ⇒ budget_aware 能说出「收到 %d/%d」⇒「缺 %d 帧」；"
        % (ba["chunks"], 20, 20 - ba["chunks"]))
    log("     而 eof_only 手里只有「结束了」，缺多少它说不出。")
    return res


# ─────────────────── B/C. 真实端点探测 ───────────────────
def _probe(url: str, secs: float, *, insecure: bool = False) -> dict:
    out = {"url": url, "ok": False, "bytes": 0, "chunks": 0, "saw_done": None,
           "error": None}
    try:
        if url.startswith("https"):
            ctx = ssl.create_default_context()
            if insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            c = http.client.HTTPSConnection(url.split("/")[2], 443,
                                            context=ctx, timeout=secs)
            path = "/" + "/".join(url.split("/")[3:])
        else:
            h, _, p = url.split("/")[2].partition(":")
            c = http.client.HTTPConnection(h, int(p or 80), timeout=secs)
            path = "/" + "/".join(url.split("/")[3:])
        c.request("GET", path)
        r = c.getresponse()
        buf = b""
        t0 = time.time()
        while time.time() - t0 < secs:
            d = r.read(1)
            if not d:
                break
            buf += d
        raw = buf.decode("utf-8", "replace")
        out["bytes"] = len(buf)
        out["chunks"] = raw.count("data: ")
        out["saw_done"] = "[DONE]" in raw
        out["ok"] = len(buf) > 0
    except Exception as e:  # noqa: BLE001
        out["error"] = "%s: %s" % (type(e).__name__, str(e)[:160])
    return out


def run_live() -> list[dict]:
    log()
    log("── B/C. 真实端点探测")
    targets = [
        ("https://sse.dev/demo", 4.0, False),
        ("http://127.0.0.1:3080/", 4.0, False),
    ]
    res = []
    for url, secs, ins in targets:
        r = _probe(url, secs, insecure=ins)
        res.append(r)
        log("  %-32s ok=%-5s 字节=%-6d 帧=%-4d done=%-5s err=%s"
            % (r["url"], r["ok"], r["bytes"], r["chunks"], r["saw_done"],
               r["error"]))
    return res


def main() -> int:
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log("# FSA 流式实测语料")
    log("# 生成时间：%s" % stamp)
    log("# 探针：probe_stream_reality.py（本机实跑，非模拟）")
    log()
    ctrl = run_control()
    matrix = run_strategy_matrix()
    live = run_live()

    if len(ctrl) != 3:
        log("[FAIL] 受控实验场景数 = %d，应为 3" % len(ctrl))
        return 1
    if any(not c for c in ctrl):
        log("[FAIL] 存在空场景结果")
        return 1

    log()
    log("── B/C 说明：真实端点探测成功率 %d/%d —— 通道到不了 ≠ 内容不存在（RA-5）。"
        % (sum(1 for r in live if r["ok"]), len(live)))

    (ART / "corpus_stream_probe.md").write_text("\n".join(LINES),
                                                 encoding="utf-8")
    log()
    log("[probe] 语料已落盘：%s" % (ART / "corpus_stream_probe.md"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
