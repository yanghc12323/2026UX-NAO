# -*- coding: utf-8 -*-
import sys
import time

# 1. 终结中文乱码魔法
reload(sys)
sys.setdefaultencoding('utf-8')

# 2. 指路牌：请把这里换成你真实的 32 位 SDK lib 路径
sys.path.insert(0, r"C:\Python27\Lib\site-packages")

import json
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

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


class CommandError(Exception):
    """协议层可预期错误。"""

    def __init__(self, error_code, message):
        self.error_code = error_code
        self.message = message
        Exception.__init__(self, message)


# ==========================================
# 🌟【关键修改 2】极简初始化逻辑
# ==========================================
def init_robot():
    global robot_controller
    try:
        if NaoBehaviorController is None:
            raise RuntimeError("naoqi_or_behavior_lib_unavailable")
        # 尝试直连真实的物理机器人
        robot_controller = NaoBehaviorController(ip="192.168.93.152")
    except Exception as e:
        print("\n[WARNING] robot connection failed; using mock controller for local debugging.\n")

        # 精简虚拟替身：专门为了让你今天能和组员测试跨端 HTTP 通信
        class MockController(object):
            def speak(self, text):
                del text
                print("[MOCK] speak")
                return True

            def nod(self): print("[MOCK] nod"); return True

            def shake_head(self): print("[MOCK] shake_head"); return True

            def stare_pressure(self): print("[MOCK] stare_pressure"); return True

            def avert_gaze(self): print("[MOCK] avert_gaze"); return True

            def reset_gaze(self): print("[MOCK] reset_gaze"); return True

            def rest(self): print("[MOCK] rest"); return True

        robot_controller = MockController()


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

    def _send_response(self, status_code, response_dict):
        self.send_response(status_code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response_dict))


if __name__ == '__main__':
    # 1. 尝试连接机器人 / 开启替身
    init_robot()

    # 2. 启动服务器监听
    httpd = HTTPServer(('', SERVER_PORT), RequestHandler)
    print("\n==============================================")
    print("[INFO] NAO interview control server started")
    print("[INFO] listen_port: %d" % SERVER_PORT)
    print("==============================================\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        httpd.socket.close()
