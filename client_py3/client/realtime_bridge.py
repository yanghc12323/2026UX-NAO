"""最小可用实时推送桥接（HTTP -> 内存缓冲）。

设计目标：
1) 不引入额外第三方依赖，仅使用标准库；
2) 外部 ASR/视觉模块可通过 HTTP POST 推送实时数据；
3) Python3 Provider 从线程安全缓冲区消费数据。
"""

from __future__ import annotations

import json
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Deque, Dict, Optional


class RealtimeStreamBridge(object):
    """实时流桥接器：承载接收服务与内存缓冲。"""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8765,
        max_asr_records: int = 200,
        max_gaze_records: int = 500,
    ):
        self.host = host
        self.port = int(port)
        self._asr_queue: Deque[dict] = deque(maxlen=max(10, int(max_asr_records)))
        self._asr_lock = threading.Lock()

        self._gaze_latest_by_stage: Dict[str, dict] = {}
        self._gaze_latest_global: Optional[dict] = None
        self._gaze_counter = 0
        self._max_gaze_records = max(20, int(max_gaze_records))
        self._gaze_lock = threading.Lock()

        self._server: Optional[ThreadingHTTPServer] = None
        self._server_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动本地 HTTP 接收服务。"""
        if self._server is not None:
            return
        self._server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        self._server_thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._server_thread.start()

    def stop(self) -> None:
        """停止本地 HTTP 接收服务。"""
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        self._server = None
        self._server_thread = None

    def publish_asr(self, payload: dict) -> None:
        with self._asr_lock:
            self._asr_queue.append(payload)

    def pop_asr_record(self) -> Optional[dict]:
        with self._asr_lock:
            if not self._asr_queue:
                return None
            return self._asr_queue.popleft()

    def publish_gaze(self, payload: dict) -> None:
        stage = str(payload.get("stage", "")).strip()
        value = float(payload.get("gaze_contact_s", 0.0) or 0.0)
        ts_ms = int(payload.get("timestamp_ms", int(time.time() * 1000)))
        record = {
            "stage": stage,
            "gaze_contact_s": max(0.0, value),
            "timestamp_ms": ts_ms,
            "_seq": self._gaze_counter,
        }

        with self._gaze_lock:
            self._gaze_counter += 1
            self._gaze_latest_global = record
            if stage:
                self._gaze_latest_by_stage[stage] = record

            # 轻量清理：超出阈值时仅保留最近 stage 的快照
            if len(self._gaze_latest_by_stage) > self._max_gaze_records:
                trimmed = sorted(
                    self._gaze_latest_by_stage.items(),
                    key=lambda kv: int(kv[1].get("_seq", 0)),
                    reverse=True,
                )[: self._max_gaze_records]
                self._gaze_latest_by_stage = dict(trimmed)

    def get_latest_gaze(self, stage: str, max_age_s: float = 2.0) -> Optional[float]:
        now_ms = int(time.time() * 1000)
        max_age_ms = int(max(0.0, float(max_age_s)) * 1000)

        with self._gaze_lock:
            stage_key = str(stage or "").strip()
            record = self._gaze_latest_by_stage.get(stage_key) if stage_key else None
            if record is None:
                record = self._gaze_latest_global
            if record is None:
                return None

            ts_ms = int(record.get("timestamp_ms", 0) or 0)
            if max_age_ms > 0 and ts_ms > 0 and (now_ms - ts_ms) > max_age_ms:
                return None
            return max(0.0, float(record.get("gaze_contact_s", 0.0) or 0.0))

    def _make_handler(self):
        bridge = self

        class _Handler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, body: dict) -> None:
                raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def _read_json_body(self) -> dict:
                size = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(size) if size > 0 else b"{}"
                text = raw.decode("utf-8") if raw else "{}"
                return json.loads(text)

            def do_GET(self):  # noqa: N802
                if self.path == "/health":
                    self._send_json(200, {"ok": True, "service": "realtime_bridge"})
                    return
                self._send_json(404, {"ok": False, "error": "not_found"})

            def do_POST(self):  # noqa: N802
                try:
                    payload = self._read_json_body()
                    if not isinstance(payload, dict):
                        self._send_json(400, {"ok": False, "error": "invalid_payload"})
                        return

                    if self.path == "/asr":
                        bridge.publish_asr(payload)
                        self._send_json(200, {"ok": True})
                        return

                    if self.path == "/gaze":
                        bridge.publish_gaze(payload)
                        self._send_json(200, {"ok": True})
                        return

                    self._send_json(404, {"ok": False, "error": "not_found"})
                except Exception as exc:  # noqa: BLE001
                    self._send_json(400, {"ok": False, "error": "bad_request", "reason": str(exc)})

            def log_message(self, fmt: str, *args):
                del fmt, args
                return

        return _Handler
