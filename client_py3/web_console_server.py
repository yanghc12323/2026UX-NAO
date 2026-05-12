# -*- coding: utf-8 -*-
"""
NAO interview manual-control web backend (Python 3).

设计目标：
1) 仅保留“主试手动控制”所需链路；
2) 移除 LLM / ASR / Gaze / 流利度计算依赖；
3) 保留会话、阶段、条件、动作指令、导出；
4) 保持与 robot_server_py2/command_server.py 的最小协议兼容。
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import threading
import time
import uuid
import asyncio
from dataclasses import dataclass, field
from http.client import RemoteDisconnected
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Dict, List, Optional
from urllib import request
from urllib.error import HTTPError, URLError

from speech_asr.asr_service import AsrService
from speech_asr.realtime_dialog_service import RealtimeDialogService


def now_ms() -> int:
    return int(time.time() * 1000)


def ts_compact() -> str:
    return time.strftime("%Y%m%d_%H%M%S", time.localtime())


STAGES = ["warmup", "introduction", "formal_interview", "closing"]


CONDITIONS = {
    "C1": {
        "label": "高人格化 × 反应式附和",
        "persona_style": "high",
        "backchanneling_type": "reactive",
    },
    "C2": {
        "label": "高人格化 × 最小附和",
        "persona_style": "high",
        "backchanneling_type": "minimal",
    },
    "C3": {
        "label": "低人格化 × 反应式附和",
        "persona_style": "low",
        "backchanneling_type": "reactive",
    },
    "C4": {
        "label": "低人格化 × 最小附和",
        "persona_style": "low",
        "backchanneling_type": "minimal",
    },
}


@dataclass
class SessionState:
    session_id: str
    participant_id: str
    participant_name: str
    condition_id: str
    persona_style: str
    backchanneling_type: str
    current_stage: str = "warmup"
    started_at_ms: int = field(default_factory=now_ms)
    ended_at_ms: int = 0
    stage_history: List[dict] = field(default_factory=list)


class ExperimentState(object):
    def __init__(self, export_dir: str, robot_server_url: str):
        self._lock = threading.RLock()
        self.export_dir = export_dir
        self.robot_server_url = robot_server_url
        self.session: Optional[SessionState] = None
        self.action_logs: List[dict] = []

        os.makedirs(self.export_dir, exist_ok=True)

    # ------------------------
    # 会话与阶段
    # ------------------------
    def start_session(self, participant_id: str, participant_name: str, condition_id: str) -> dict:
        if not participant_id:
            raise ValueError("participant_id_required")
        if not participant_name:
            raise ValueError("participant_name_required")
        if condition_id not in CONDITIONS:
            raise ValueError("invalid_condition_id")

        cond = CONDITIONS[condition_id]
        sid = "S_%s_%s" % (ts_compact(), uuid.uuid4().hex[:6].upper())
        s = SessionState(
            session_id=sid,
            participant_id=participant_id,
            participant_name=participant_name,
            condition_id=condition_id,
            persona_style=cond["persona_style"],
            backchanneling_type=cond["backchanneling_type"],
        )
        s.stage_history.append({"stage": s.current_stage, "timestamp_ms": now_ms(), "source": "session_start"})

        with self._lock:
            self.session = s
            self.action_logs = []

        return {"ok": True, "session": self._session_public(s)}

    def end_session(self) -> dict:
        with self._lock:
            if self.session is None:
                return {"ok": False, "error": "no_active_session"}
            self.session.ended_at_ms = now_ms()
            s = self.session
        return {"ok": True, "session": self._session_public(s)}

    def set_stage(self, stage: str, source: str = "manual") -> dict:
        stage = str(stage or "").strip()
        if stage not in STAGES:
            raise ValueError("invalid_stage")
        with self._lock:
            if self.session is None:
                raise ValueError("no_active_session")
            self.session.current_stage = stage
            self.session.stage_history.append({"stage": stage, "timestamp_ms": now_ms(), "source": source})
            s = self.session
        return {"ok": True, "session": self._session_public(s)}

    # ------------------------
    # 机器人命令
    # ------------------------
    def send_robot_command(self, command: str, payload: dict, label: str = "") -> dict:
        body = {
            "protocol_version": "1.0",
            "request_id": "WEB_%s" % uuid.uuid4().hex[:12].upper(),
            "timestamp_ms": now_ms(),
            "command": str(command),
            "payload": payload or {},
            "timeout_ms": 15000 if command == "speak" else 5000,
            "retry_count": 0,
        }
        if self.session is not None:
            body["session_id"] = self.session.session_id
            body["participant_id"] = self.session.participant_id
            body["condition_id"] = self.session.condition_id

        started = now_ms()
        stage = self.session.current_stage if self.session else "no_session"
        log_item = {
            "timestamp_ms": started,
            "stage": stage,
            "label": label or "",
            "command": str(command),
            "payload": payload or {},
            "status": "error",
            "message": "",
            "response": None,
            "latency_ms": 0,
        }

        # 最小化稳定性增强：对“连接被对端关闭/瞬时拒绝/超时”做 1 次短重试。
        # speak 保持更长超时；其余命令保持短超时。
        attempts = 2
        timeout_s = 20.0 if command == "speak" else 6.0
        retryable_errno = {10053, 10054, 10060, 10061}
        last_exc = None

        def _is_retryable(exc: Exception) -> bool:
            if isinstance(exc, (RemoteDisconnected, TimeoutError, socket.timeout)):
                return True
            if isinstance(exc, URLError):
                reason = getattr(exc, "reason", None)
                if isinstance(reason, socket.timeout):
                    return True
                winerr = getattr(reason, "winerror", None)
                if winerr in retryable_errno:
                    return True
                if isinstance(reason, OSError) and getattr(reason, "errno", None) in retryable_errno:
                    return True
                txt = str(reason).lower() if reason is not None else str(exc).lower()
                for key in ["timed out", "remote end closed", "connection reset", "connection aborted", "connection refused"]:
                    if key in txt:
                        return True
            return False

        def _post_once(body_dict: dict, timeout_seconds: float) -> dict:
            req = request.Request(
                self.robot_server_url,
                data=json.dumps(body_dict, ensure_ascii=False).encode("utf-8"),
                headers={"Content-Type": "application/json; charset=utf-8"},
            )
            with request.urlopen(req, timeout=timeout_seconds) as resp:
                raw = resp.read().decode("utf-8")
            return json.loads(raw)

        def _compat_fallback(orig_cmd: str, orig_payload: dict, req_body: dict) -> Optional[dict]:
            """
            当现场误连旧版 command_server（不识别新命令）时，做一次最小兼容回退。
            仅在明确 invalid_command_* 时触发，避免影响正常链路。
            """
            c = str(orig_cmd or "")
            fallback = None
            if c == "think_chin":
                fallback = {"command": "gesture", "payload": {"name": "thinking_chin_touch"}}
            elif c == "arms_crossed":
                fallback = {"command": "gesture", "payload": {"name": "pressure_arms_crossed"}}
            elif c == "hands_on_hips":
                fallback = {"command": "gesture", "payload": {"name": "pressure_hands_on_hips"}}
            elif c == "gaze" and str((orig_payload or {}).get("target", "")).lower() in ["away", "down_left", "down_right"]:
                # 兼容非常旧的实现：仅支持 legacy avert_gaze。
                fallback = {"command": "avert_gaze", "payload": {}}
            if not fallback:
                return None

            fb_body = dict(req_body)
            fb_body["command"] = fallback["command"]
            fb_body["payload"] = fallback.get("payload", {})
            fb_data = _post_once(fb_body, timeout_s)
            if isinstance(fb_data, dict):
                fb_data.setdefault("compat", {})
                fb_data["compat"] = {
                    "fallback_used": True,
                    "from_command": c,
                    "to_command": fallback["command"],
                }
            return fb_data

        try:
            for i in range(attempts):
                try:
                    data = _post_once(body, timeout_s)
                    status = str(data.get("status", "")).lower()

                    # 命令可达但不识别：现场常见于“启动了旧版 Python2 command_server”。
                    # 这里做一次兼容回退，降低调试阻塞。
                    if status != "ok":
                        err_msg = str(data.get("message", ""))
                        err_code = str(data.get("error_code", ""))
                        if err_code == "E102" and err_msg.startswith("invalid_command_"):
                            fb = _compat_fallback(command, payload or {}, body)
                            if fb is not None:
                                data = fb
                                status = str(data.get("status", "")).lower()

                    log_item["status"] = "ok" if status == "ok" else "error"
                    msg = str(data.get("message", ""))
                    if i > 0:
                        msg = "retried_%d;%s" % (i, msg)
                    if isinstance(data, dict) and data.get("compat", {}).get("fallback_used"):
                        c = data.get("compat", {})
                        msg = "compat_fallback:%s->%s;%s" % (
                            str(c.get("from_command", "")),
                            str(c.get("to_command", "")),
                            msg,
                        )
                    log_item["message"] = msg
                    log_item["response"] = data
                    return data
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if i < attempts - 1 and _is_retryable(exc):
                        time.sleep(0.2)
                        continue
                    raise
        except (HTTPError, URLError) as exc:
            log_item["message"] = "network_error:%s" % str(exc)
            return {
                "status": "error",
                "error_code": "E_NET",
                "message": log_item["message"],
                "result": {},
            }
        except Exception as exc:  # noqa: BLE001
            if last_exc is not None:
                log_item["message"] = "command_failed:%s" % str(last_exc)
            else:
                log_item["message"] = "command_failed:%s" % str(exc)
            return {
                "status": "error",
                "error_code": "E_FAIL",
                "message": log_item["message"],
                "result": {},
            }
        finally:
            log_item["latency_ms"] = max(0, now_ms() - started)
            with self._lock:
                self.action_logs.append(log_item)
                if len(self.action_logs) > 3000:
                    self.action_logs = self.action_logs[-3000:]

    def command_server_health(self) -> dict:
        checked_at = now_ms()
        body = {
            "protocol_version": "1.0",
            "request_id": "WEB_HEALTH_%s" % uuid.uuid4().hex[:8].upper(),
            "timestamp_ms": checked_at,
            "command": "ping",
            "payload": {},
            "timeout_ms": 2500,
            "retry_count": 0,
        }
        req = request.Request(
            self.robot_server_url,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        try:
            with request.urlopen(req, timeout=3.0) as resp:
                raw = resp.read().decode("utf-8")
            data = json.loads(raw)
            ok = str(data.get("status", "")).lower() == "ok"
            return {
                "checked_at_ms": checked_at,
                "ok": ok,
                "message": str(data.get("message", "")),
                "url": self.robot_server_url,
                "raw": data,
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "checked_at_ms": checked_at,
                "ok": False,
                "message": "health_probe_failed:%s" % str(exc),
                "url": self.robot_server_url,
                "raw": {},
            }

    # ------------------------
    # 阶段脚本（可手动单步执行）
    # ------------------------
    def build_stage_script(self, stage: str) -> List[dict]:
        s = self.session
        name = (s.participant_name if s else "同学")
        persona = (s.persona_style if s else "high")
        backchannel = (s.backchanneling_type if s else "reactive")

        encourage = "你可以慢慢来，我在认真听。" if persona == "high" else "请开始。"
        bc_nod = 2 if backchannel == "reactive" else 1

        scripts = {
            "warmup": [
                {
                    "label": "热身开场",
                    "command": "speak",
                    "payload": {"text": "你好%s，欢迎来到模拟面试。我们先轻松聊两句。" % name},
                },
                {
                    "label": "热身提问",
                    "command": "speak",
                    "payload": {"text": "今天天气怎么样？或者你今天心情如何？"},
                },
                {"label": "热身附和", "command": "nod", "payload": {"count": bc_nod}},
            ],
            "introduction": [
                {
                    "label": "介绍实验规则",
                    "command": "speak",
                    "payload": {
                        "text": "接下来是实验说明：本实验包含热身、正式面试与收尾。请你自然作答，内容仅用于研究分析。"
                    },
                },
                {
                    "label": "说明阶段安排",
                    "command": "speak",
                    "payload": {"text": "正式阶段先进行30秒自我介绍，随后我会基于STAR法则逐个提4个问题。"},
                },
            ],
            "formal_interview": [
                {
                    "label": "正式开场",
                    "command": "speak",
                    "payload": {"text": "现在进入正式面试。首先请你用30秒做一个自我介绍。%s" % encourage},
                },
                {"label": "Q1-S", "command": "speak", "payload": {"text": "问题一（Situation）：请描述一个你曾面对压力任务的具体情境。"}},
                {"label": "Q1-附和", "command": "nod", "payload": {"count": bc_nod}},
                {"label": "Q2-T", "command": "speak", "payload": {"text": "问题二（Task）：在那个情境下，你的核心目标和责任是什么？"}},
                {"label": "Q2-附和", "command": "nod", "payload": {"count": bc_nod}},
                {"label": "Q3-A", "command": "speak", "payload": {"text": "问题三（Action）：你具体采取了哪些行动？请尽量按步骤说明。"}},
                {"label": "Q3-附和", "command": "nod", "payload": {"count": bc_nod}},
                {"label": "Q4-R", "command": "speak", "payload": {"text": "问题四（Result）：最后结果如何？你从中学到了什么？"}},
                {"label": "Q4-附和", "command": "nod", "payload": {"count": bc_nod}},
            ],
            "closing": [
                {
                    "label": "结束语",
                    "command": "speak",
                    "payload": {"text": "本次实验到这里结束。感谢你的参与，请联系主试填写后测问卷。"},
                },
                {"label": "收尾点头", "command": "nod", "payload": {"count": 1}},
                {"label": "复位姿态", "command": "reset_posture", "payload": {}},
            ],
        }
        return scripts.get(stage, [])

    def execute_stage_step(self, stage: str, step_index: int) -> dict:
        if stage not in STAGES:
            raise ValueError("invalid_stage")
        steps = self.build_stage_script(stage)
        if step_index < 0 or step_index >= len(steps):
            raise ValueError("invalid_step_index")
        step = steps[step_index]
        resp = self.send_robot_command(step["command"], step.get("payload", {}), label=step.get("label", ""))
        return {
            "ok": True,
            "stage": stage,
            "step_index": step_index,
            "step": step,
            "robot_response": resp,
        }

    def execute_stage_all(self, stage: str, stop_on_error: bool = False) -> dict:
        if stage not in STAGES:
            raise ValueError("invalid_stage")
        rows = []
        for idx, step in enumerate(self.build_stage_script(stage)):
            resp = self.send_robot_command(step["command"], step.get("payload", {}), label=step.get("label", ""))
            ok = str(resp.get("status", "")).lower() == "ok"
            rows.append({"step_index": idx, "step": step, "ok": ok, "robot_response": resp})
            if stop_on_error and not ok:
                break
        return {"ok": True, "stage": stage, "results": rows}

    # ------------------------
    # 导出
    # ------------------------
    def export_session(self) -> dict:
        with self._lock:
            if self.session is None:
                return {"ok": False, "error": "no_active_session"}
            s = self.session
            logs = list(self.action_logs)

        out = os.path.join(self.export_dir, "%s_%s_manual.csv" % (s.session_id, ts_compact()))
        self._export_csv(s, logs, out)
        return {"ok": True, "file_type": "csv", "file_path": out}

    @staticmethod
    def _export_csv(session: SessionState, logs: List[dict], out_path: str) -> None:
        import csv

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["session_id", session.session_id])
            w.writerow(["participant_id", session.participant_id])
            w.writerow(["participant_name", session.participant_name])
            w.writerow(["condition_id", session.condition_id])
            w.writerow(["persona_style", session.persona_style])
            w.writerow(["backchanneling_type", session.backchanneling_type])
            w.writerow(["started_at_ms", session.started_at_ms])
            w.writerow(["ended_at_ms", session.ended_at_ms])
            w.writerow([])

            w.writerow(["stage_history"])
            w.writerow(["stage", "timestamp_ms", "source"])
            for r in session.stage_history:
                w.writerow([r.get("stage", ""), r.get("timestamp_ms", 0), r.get("source", "")])
            w.writerow([])

            w.writerow(["action_logs"])
            w.writerow(["timestamp_ms", "stage", "label", "command", "payload", "status", "message", "latency_ms", "response"])
            for r in logs:
                w.writerow([
                    r.get("timestamp_ms", 0),
                    r.get("stage", ""),
                    r.get("label", ""),
                    r.get("command", ""),
                    json.dumps(r.get("payload", {}), ensure_ascii=False),
                    r.get("status", ""),
                    r.get("message", ""),
                    r.get("latency_ms", 0),
                    json.dumps(r.get("response", {}), ensure_ascii=False),
                ])

    # ------------------------
    # 状态
    # ------------------------
    def status(self) -> dict:
        with self._lock:
            s = self.session
            logs = list(self.action_logs[-50:])

        stage = s.current_stage if s else "warmup"
        return {
            "ok": True,
            "mode": "manual_script_only",
            "stages": STAGES,
            "conditions": CONDITIONS,
            "session": self._session_public(s) if s else None,
            "stage_script": self.build_stage_script(stage),
            "recent_actions": logs,
            "counts": {"action_logs": len(self.action_logs)},
            "connectivity": {
                "command_server": self.command_server_health(),
                "asr": {"ok": False, "disabled": True, "message": "removed_in_manual_mode"},
                "gaze": {"ok": False, "disabled": True, "message": "removed_in_manual_mode"},
            },
        }

    @staticmethod
    def _session_public(s: SessionState) -> dict:
        return {
            "session_id": s.session_id,
            "participant_id": s.participant_id,
            "participant_name": s.participant_name,
            "condition_id": s.condition_id,
            "persona_style": s.persona_style,
            "backchanneling_type": s.backchanneling_type,
            "current_stage": s.current_stage,
            "started_at_ms": s.started_at_ms,
            "ended_at_ms": s.ended_at_ms,
            "stage_history": s.stage_history,
        }


class WebConsoleServer(object):
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 8780,
        static_dir: Optional[str] = None,
        export_dir: str = "client_py3/exports",
        robot_server_url: str = "http://127.0.0.1:8000/command",
    ):
        self.host = host
        self.port = int(port)
        self.static_dir = static_dir or os.path.join(os.path.dirname(__file__), "web_console")
        self.state = ExperimentState(export_dir=export_dir, robot_server_url=robot_server_url)
        self.asr = AsrService()
        self.realtime = RealtimeDialogService(
            speak_func=lambda text, label: self.state.send_robot_command("speak", {"text": text}, label=label),
            state_provider=lambda: self.state.status(),
        )
        self._server: Optional[ThreadingHTTPServer] = None
        self._ws_thread: Optional[threading.Thread] = None
        self._ws_loop = None
        self._ws_port = self.port + 1
        self._ws_started = False
        self._ws_error = ""

    def _find_available_port(self, host: str, start_port: int, max_tries: int = 20) -> int:
        for p in range(start_port, start_port + max_tries):
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                s.bind((host, p))
                return p
            except OSError:
                continue
            finally:
                try:
                    s.close()
                except Exception:
                    pass
        raise OSError("no_available_ws_port_from_%d" % start_port)

    def _start_realtime_ws(self) -> None:
        def _runner():
            try:
                import websockets
            except Exception:
                print("[WARN] websockets not installed, realtime ws disabled")
                self._ws_started = False
                self._ws_error = "websockets_not_installed"
                return

            try:
                selected_port = self._find_available_port(self.host, self.port + 1, max_tries=30)
                self._ws_port = selected_port

                async def _main():
                    async with websockets.serve(self.realtime.handle_ws, self.host, self._ws_port, max_size=2**22):
                        self._ws_started = True
                        self._ws_error = ""
                        if self._ws_port != self.port + 1:
                            print("[WARN] realtime_ws_port_conflict: %d occupied, fallback to %d" % (self.port + 1, self._ws_port))
                        print("[INFO] realtime_ws_started: ws://%s:%d/ws/realtime-dialog" % (self.host, self._ws_port))
                        await asyncio.Future()

                loop = asyncio.new_event_loop()
                self._ws_loop = loop
                asyncio.set_event_loop(loop)
                loop.run_until_complete(_main())
            except Exception as exc:  # noqa: BLE001
                self._ws_started = False
                self._ws_error = str(exc)
                print("[WARN] realtime_ws_start_failed:%s" % self._ws_error)

        self._ws_thread = threading.Thread(target=_runner, name="realtime-ws", daemon=True)
        self._ws_thread.start()

    def start(self) -> None:
        self._start_realtime_ws()
        self._server = ThreadingHTTPServer((self.host, self.port), self._make_handler())
        print("[INFO] web_console_started: http://%s:%d" % (self.host, self.port))
        print("[INFO] robot_server_url=%s" % self.state.robot_server_url)
        self._server.serve_forever()

    def _make_handler(self):
        outer = self
        state = self.state
        asr = self.asr
        realtime = self.realtime
        static_dir = self.static_dir

        class _Handler(BaseHTTPRequestHandler):
            def _send_json(self, status: int, body: dict) -> None:
                raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                try:
                    self.wfile.write(raw)
                except Exception:
                    return

            def _read_json(self) -> dict:
                size = int(self.headers.get("Content-Length", "0") or 0)
                raw = self.rfile.read(size) if size > 0 else b"{}"
                return json.loads(raw.decode("utf-8"))

            def _serve_index(self) -> None:
                path = os.path.join(static_dir, "index.html")
                if not os.path.isfile(path):
                    self._send_json(404, {"ok": False, "error": "index_not_found"})
                    return
                with open(path, "rb") as f:
                    raw = f.read()
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def do_GET(self):  # noqa: N802
                if self.path in ["/", "/index.html"]:
                    self._serve_index()
                    return
                if self.path == "/api/health":
                    self._send_json(200, {"ok": True, "service": "web_console"})
                    return
                if self.path == "/api/status":
                    s = state.status()
                    s["asr"] = asr.status()
                    s["realtime_dialog"] = realtime.status()
                    s["realtime_dialog"]["ws_url"] = "ws://%s:%d/ws/realtime-dialog" % (self.server.server_address[0], outer._ws_port)
                    s["realtime_dialog"]["ws_started"] = outer._ws_started
                    s["realtime_dialog"]["ws_error"] = outer._ws_error
                    s["robot_action_support"] = {
                        "web_supported_commands": [
                            "speak",
                            "nod",
                            "gaze",
                            "think_chin",
                            "arms_crossed",
                            "hands_on_hips",
                            "gesture",
                            "reset_posture",
                            "perform_sequence",
                            "shake_head",
                            "stare",
                            "avert_gaze",
                            "rest",
                            "ping",
                        ],
                        "note": "已完成代码链路检查；实机动作可用性需在机器人在线时逐项点击验证。",
                    }
                    self._send_json(200, s)
                    return
                self._send_json(404, {"ok": False, "error": "not_found"})

            def do_POST(self):  # noqa: N802
                try:
                    if self.path == "/asr" or self.path == "/gaze":
                        # 手动模式下保留兼容入口，避免旧推送脚本报错。
                        _ = self._read_json()
                        self._send_json(200, {"ok": True, "ignored": True, "mode": "manual_script_only"})
                        return

                    if self.path == "/api/session/start":
                        p = self._read_json()
                        ret = state.start_session(
                            participant_id=str(p.get("participant_id", "")).strip(),
                            participant_name=str(p.get("participant_name", "")).strip(),
                            condition_id=str(p.get("condition_id", "")).strip(),
                        )
                        self._send_json(200, ret)
                        return

                    if self.path == "/api/session/end":
                        ret = state.end_session()
                        ret["export"] = state.export_session()
                        self._send_json(200, ret)
                        return

                    if self.path == "/api/session/export":
                        self._send_json(200, state.export_session())
                        return

                    if self.path == "/api/stage":
                        p = self._read_json()
                        stage = str(p.get("stage", "")).strip()
                        ret = state.set_stage(stage=stage, source="web_manual")
                        ret["stage_script"] = state.build_stage_script(stage)
                        self._send_json(200, ret)
                        return

                    if self.path == "/api/stage/step":
                        p = self._read_json()
                        stage = str(p.get("stage", "")).strip()
                        idx = int(p.get("step_index", -1))
                        self._send_json(200, state.execute_stage_step(stage, idx))
                        return

                    if self.path == "/api/stage/run":
                        p = self._read_json()
                        stage = str(p.get("stage", "")).strip()
                        stop_on_error = bool(p.get("stop_on_error", False))
                        self._send_json(200, state.execute_stage_all(stage, stop_on_error=stop_on_error))
                        return

                    if self.path == "/api/robot/command":
                        p = self._read_json()
                        cmd = str(p.get("command", "")).strip()
                        payload = p.get("payload", {})
                        label = str(p.get("label", "manual_command")).strip() or "manual_command"
                        if not cmd:
                            self._send_json(400, {"ok": False, "error": "missing_command"})
                            return
                        if payload is None:
                            payload = {}
                        if not isinstance(payload, dict):
                            self._send_json(400, {"ok": False, "error": "invalid_payload"})
                            return
                        data = state.send_robot_command(cmd, payload, label=label)
                        self._send_json(200, {"ok": True, "robot_response": data})
                        return

                    if self.path == "/api/asr/config":
                        p = self._read_json()
                        self._send_json(200, asr.update_config(p))
                        return

                    if self.path == "/api/asr/start":
                        self._send_json(200, asr.start())
                        return

                    if self.path == "/api/asr/stop":
                        self._send_json(200, asr.stop())
                        return

                    if self.path == "/api/asr/chunk":
                        p = self._read_json()
                        audio_base64 = str(p.get("audio_base64", "")).strip()
                        mime_type = str(p.get("mime_type", "audio/webm")).strip() or "audio/webm"
                        if not audio_base64:
                            self._send_json(400, {"ok": False, "error": "audio_base64_required"})
                            return
                        self._send_json(200, asr.accept_chunk(audio_base64=audio_base64, mime_type=mime_type))
                        return

                    if self.path == "/api/realtime/config":
                        p = self._read_json()
                        self._send_json(200, realtime.update_config(p))
                        return

                    self._send_json(404, {"ok": False, "error": "not_found"})
                except ValueError as exc:
                    self._send_json(400, {"ok": False, "error": str(exc)})
                except Exception as exc:  # noqa: BLE001
                    self._send_json(500, {"ok": False, "error": "internal_error", "reason": str(exc)})

            def log_message(self, fmt: str, *args):
                del fmt, args
                return

        return _Handler


def _parse_args():
    parser = argparse.ArgumentParser(description="NAO 实验 Web 控制台（手动脚本模式）")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Web 服务监听地址")
    parser.add_argument("--port", type=int, default=8780, help="Web 服务监听端口")
    parser.add_argument(
        "--robot-server-url",
        type=str,
        default="http://127.0.0.1:8000/command",
        help="Python2 command_server 的 URL",
    )
    parser.add_argument(
        "--export-dir",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "exports"),
        help="实验数据导出目录（csv）",
    )
    parser.add_argument(
        "--static-dir",
        type=str,
        default=os.path.join(os.path.dirname(__file__), "web_console"),
        help="前端静态文件目录",
    )
    return parser.parse_args()


def main():
    args = _parse_args()
    server = WebConsoleServer(
        host=args.host,
        port=args.port,
        static_dir=args.static_dir,
        export_dir=args.export_dir,
        robot_server_url=args.robot_server_url,
    )
    server.start()


if __name__ == "__main__":
    main()
