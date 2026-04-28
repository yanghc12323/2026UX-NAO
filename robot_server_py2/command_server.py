# -*- coding: utf-8 -*-
import sys
import time
import os
import argparse

# 1. 终结中文乱码魔法
reload(sys)
sys.setdefaultencoding('utf-8')

# 2. 真实的 32 位 SDK lib 路径
sys.path.insert(0, r"C:\Python27\Lib\site-packages")

import json
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
import socket

# 🌟【关键修改 1】导入我们刚刚写好的高压行为核心库
try:
    from nao_behavior_lib import NaoBehaviorController
except Exception:
    NaoBehaviorController = None

# ==========================================
# 全局配置与变量
# ==========================================
SERVER_PORT = 8000
robot_controller = None  # 唯一的全局控制器对象
SERVER_START_MS = int(time.time() * 1000)
CONTROLLER_MODE = "unknown"
ROBOT_ENDPOINT = ""


class CommandError(Exception):
    """协议层可预期错误。"""

    def __init__(self, error_code, message):
        self.error_code = error_code
        self.message = message
        Exception.__init__(self, message)


# ==========================================
# 机器人初始化
# ==========================================
def init_robot(robot_ip, robot_port):
    """初始化真实NAO机器人连接"""
    global robot_controller, CONTROLLER_MODE, ROBOT_ENDPOINT
    ROBOT_ENDPOINT = "%s:%s" % (robot_ip, robot_port)
    
    if NaoBehaviorController is None:
        raise RuntimeError("naoqi_or_behavior_lib_unavailable")
    
    robot_controller = NaoBehaviorController(ip=robot_ip, port=robot_port)
    CONTROLLER_MODE = "real"
    print("[INFO] robot controller connected: %s" % ROBOT_ENDPOINT)


def now_ms():
    return int(time.time() * 1000)


def build_response(req, status, error_code, message, result):
    """统一响应结构（与 Python3 CommandResponse 对齐）。"""
    req = req or {}
    return {
        "protocol_version": str(req.get("protocol_version", "1.0")),
        "request_id": str(req.get("request_id", "")),
        "server_timestamp_ms": now_ms(),
        "status": status,
        "error_code": error_code,
        "message": message,
        "result": result or {},
    }


def normalize_request(raw_data):
    """兼容 legacy 简化请求，并标准化为 v1 请求结构。"""
    if not isinstance(raw_data, dict):
        raise CommandError("E100", "invalid_json_object")

    command = raw_data.get("command")
    if not command:
        raise CommandError("E101", "missing_field_command")

    payload = raw_data.get("payload", {})
    if payload is None:
        payload = {}
    if not isinstance(payload, dict):
        raise CommandError("E103", "invalid_payload_payload_must_be_object")

    req = {
        "protocol_version": str(raw_data.get("protocol_version", "1.0")),
        "request_id": str(raw_data.get("request_id", "REQ_LEGACY_%s" % now_ms())),
        "timestamp_ms": int(raw_data.get("timestamp_ms", now_ms()) or now_ms()),
        "session_id": str(raw_data.get("session_id", "legacy_session")),
        "participant_id": str(raw_data.get("participant_id", "legacy_participant")),
        "condition_id": str(raw_data.get("condition_id", "legacy_condition")),
        "turn_id": str(raw_data.get("turn_id", "T000")),
        "command": str(command),
        "payload": payload,
        "timeout_ms": int(raw_data.get("timeout_ms", 5000) or 5000),
        "retry_count": int(raw_data.get("retry_count", 0) or 0),
    }
    return req


def _route_gaze(target):
    target = (target or "user").lower()
    if target in ["user", "neutral"]:
        robot_controller.reset_gaze()
        return {"applied_target": target, "mapped_action": "reset_gaze"}
    if target in ["down_left", "down_right", "away"]:
        robot_controller.avert_gaze()
        return {"applied_target": target, "mapped_action": "avert_gaze"}
    raise CommandError("E103", "invalid_payload_target")


def _route_gesture(name):
    # 最小可用映射：后续可按实验脚本再扩展
    mapping = {
        "encourage_open_palm": "nod",
        "approval_nod": "nod",
        "disapproval_shake": "shake_head",
    }
    action = mapping.get(name)
    if not action:
        raise CommandError("E102", "invalid_command_gesture_name")
    if action == "nod":
        robot_controller.nod()
    elif action == "shake_head":
        robot_controller.shake_head()
    return {"gesture": name, "mapped_action": action}


# ==========================================
# 🌟【关键修改 3】统一的指令路由表 (彻底解耦)
# ==========================================
def route_command(command, payload):
    """将字符串命令映射到 robot_controller 的具体物理动作上"""
    cmd = str(command)

    # ---- canonical 命令（以 Python3 协议为准）----
    if cmd == "ping":
        return {
            "alive": True,
            "server_uptime_ms": now_ms() - SERVER_START_MS,
            "controller_mode": CONTROLLER_MODE,
            "robot_endpoint": ROBOT_ENDPOINT,
        }

    if cmd == "speak":
        text = payload.get("text", "")
        if not text:
            raise CommandError("E103", "invalid_payload_text_empty")
        robot_controller.speak(text)
        return {"command": cmd}

    if cmd == "nod":
        count = int(payload.get("count", 1) or 1)
        count = max(1, min(5, count))
        for _ in range(count):
            robot_controller.nod()
        return {"command": cmd, "count": count}

    if cmd == "gaze":
        mapped = _route_gaze(payload.get("target", "user"))
        return mapped

    if cmd == "reset_posture":
        robot_controller.reset_gaze()
        return {"command": cmd, "mapped_action": "reset_gaze"}

    if cmd == "gesture":
        name = payload.get("name", "")
        if not name:
            raise CommandError("E103", "invalid_payload_gesture_name_empty")
        return _route_gesture(str(name))

    if cmd == "perform_sequence":
        steps = payload.get("steps", [])
        stop_on_error = bool(payload.get("stop_on_error", True))
        if not isinstance(steps, list):
            raise CommandError("E103", "invalid_payload_steps_must_be_list")

        step_results = []
        for idx, step in enumerate(steps):
            if not isinstance(step, dict):
                err = {"step": idx, "status": "error", "error_code": "E103", "message": "invalid_step_object"}
                step_results.append(err)
                if stop_on_error:
                    raise CommandError("E103", "invalid_payload_sequence_step")
                continue

            step_cmd = step.get("command")
            step_payload = step.get("payload", {})
            try:
                data = route_command(step_cmd, step_payload)
                step_results.append({"step": idx, "status": "ok", "error_code": "E000", "result": data})
            except CommandError as ce:
                step_results.append({"step": idx, "status": "error", "error_code": ce.error_code, "message": ce.message})
                if stop_on_error:
                    raise ce

        return {
            "command": cmd,
            "step_results": step_results,
        }

    # ---- legacy 命令（兼容 Python2 旧脚本）----
    if cmd == "shake_head":
        robot_controller.shake_head()
        return {"command": cmd}
    if cmd == "stare":
        robot_controller.stare_pressure()
        return {"command": cmd, "mapped_action": "stare_pressure"}
    if cmd == "avert_gaze":
        robot_controller.avert_gaze()
        return {"command": cmd}
    if cmd == "reset_gaze":
        robot_controller.reset_gaze()
        return {"command": cmd}
    if cmd == "rest":
        robot_controller.rest()
        return {"command": cmd}

    raise CommandError("E102", "invalid_command_%s" % cmd)


# ==========================================
# HTTP 服务器逻辑 (几乎不需要改动)
# ==========================================
class RequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/command':
            content_length = int(self.headers.getheader('content-length', 0))
            post_data = self.rfile.read(content_length)
            try:
                req_json = json.loads(post_data)
            except Exception:
                resp = build_response(
                    req={"protocol_version": "1.0", "request_id": ""},
                    status="error",
                    error_code="E100",
                    message="invalid_json",
                    result={"execution_ms": 0, "robot_state": "idle"},
                )
                self._send_response(200, resp)
                return

            req_obj = None
            started = now_ms()
            try:
                req_obj = normalize_request(req_json)
                command = req_obj.get("command")
                payload = req_obj.get("payload", {})

                print("\n" + "=" * 45)
                print("[HTTP] request_id=%s command=%s" % (req_obj.get("request_id"), command))

                # 调用上面的路由函数
                action_result = route_command(command, payload)
                exec_ms = max(0, now_ms() - started)
                result = {
                    "execution_ms": exec_ms,
                    "robot_state": "idle",
                }
                result.update(action_result or {})
                resp = build_response(
                    req=req_obj,
                    status="ok",
                    error_code="E000",
                    message="success",
                    result=result,
                )
                self._send_response(200, resp)

            except CommandError as ce:
                print("[ERROR] protocol_or_command_error: %s" % ce.message)
                exec_ms = max(0, now_ms() - started)
                resp = build_response(
                    req=req_obj,
                    status="error",
                    error_code=ce.error_code,
                    message=ce.message,
                    result={"execution_ms": exec_ms, "robot_state": "idle"},
                )
                self._send_response(200, resp)
            except Exception as e:
                print("[ERROR] command_execution_exception: %s" % str(e))
                exec_ms = max(0, now_ms() - started)
                resp = build_response(
                    req=req_obj,
                    status="error",
                    error_code="E500",
                    message="internal_server_error",
                    result={"execution_ms": exec_ms, "robot_state": "idle"},
                )
                self._send_response(200, resp)
        else:
            resp = build_response(
                req={"protocol_version": "1.0", "request_id": ""},
                status="error",
                error_code="E102",
                message="invalid_path",
                result={"execution_ms": 0, "robot_state": "idle"},
            )
            self._send_response(404, resp)

    def log_message(self, format, *args):
        # 静默 BaseHTTPServer 默认日志，避免污染调试输出
        return

    def finish(self):
        """忽略客户端超时/主动断开导致的 flush 异常（Windows 常见 Errno 10053）。"""
        try:
            if not self.wfile.closed:
                self.wfile.flush()
        except socket.error as e:
            print("[WARN] client_disconnected_during_flush: %s" % str(e))
        finally:
            try:
                self.wfile.close()
            except Exception:
                pass
            try:
                self.rfile.close()
            except Exception:
                pass

    def _send_response(self, status_code, response_dict):
        raw = json.dumps(response_dict)
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Connection', 'close')
        self.end_headers()
        try:
            self.wfile.write(raw)
        except socket.error as e:
            # 客户端（通常是 Python3 端）超时后会主动断开，服务端写回时会触发 10053。
            print("[WARN] client_disconnected_before_response_write: %s" % str(e))
        self.close_connection = True


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="NAO command server (Python2)")
    parser.add_argument("--robot-ip", default=os.environ.get("NAO_ROBOT_IP", "192.168.93.152"))
    parser.add_argument("--robot-port", type=int, default=int(os.environ.get("NAO_ROBOT_PORT", "9559")))
    parser.add_argument("--port", type=int, default=int(os.environ.get("COMMAND_SERVER_PORT", SERVER_PORT)))
    args = parser.parse_args()

    # 连接真实NAO机器人
    init_robot(robot_ip=args.robot_ip, robot_port=args.robot_port)

    # 2. 启动服务器监听
    httpd = HTTPServer(('', args.port), RequestHandler)
    print("\n==============================================")
    print("[INFO] NAO interview control server started")
    print("[INFO] listen_port: %d" % args.port)
    print("[INFO] robot_endpoint: %s" % ROBOT_ENDPOINT)
    print("[INFO] controller_mode: %s" % CONTROLLER_MODE)
    print("==============================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.socket.close()
