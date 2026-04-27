"""机器人动作适配器。

该层向上提供“语义化接口”，向下调用 `CommandClient.send`：
- 上层业务（实验状态机 / LLM 控制器）只需调用 speak/nod/gaze 等函数；
- 协议字段细节集中在本层处理，便于后续维护和演进。
"""

from typing import Any, Dict, List, Optional

from .command_client import CommandClient
from .models import CommandResponse


class RobotActionAdapter(object):
    """机器人动作高层 API。"""

    def __init__(self, command_client: CommandClient):
        self.command_client = command_client

    # ------------------------
    # 基础控制
    # ------------------------
    def ping(self) -> CommandResponse:
        """健康检查。"""
        return self.command_client.send("ping", payload={})

    def reset(self, posture: str = "stand_init") -> CommandResponse:
        """恢复默认姿态。"""
        return self.command_client.send("reset_posture", payload={"posture": posture})

    # ------------------------
    # 语音输出
    # ------------------------
    def speak(
        self,
        text: str,
        voice: str = "default",
        speed: int = 95,
        volume: int = 70,
        interrupt: bool = False,
        timeout_ms: Optional[int] = None,
    ) -> CommandResponse:
        """TTS 播报。

        参数说明：
        - text: 必填，非空。
        - speed: 协议建议范围 50~200。
        - volume: 协议建议范围 0~100。
        """
        if not text or not text.strip():
            # 与协议 E103 对齐：参数非法
            return self._local_invalid_payload("text is empty")

        payload = {
            "text": text,
            "voice": voice,
            "speed": self._clamp(speed, 50, 200),
            "volume": self._clamp(volume, 0, 100),
            "interrupt": bool(interrupt),
        }
        return self.command_client.send("speak", payload=payload, timeout_ms=timeout_ms)

    # ------------------------
    # 非语言行为（backchannel）
    # ------------------------
    def nod(self, count: int = 1, amplitude: str = "small", tempo: str = "normal") -> CommandResponse:
        """点头反馈。"""
        payload = {
            "count": self._clamp(int(count), 1, 5),
            "amplitude": amplitude,
            "tempo": tempo,
        }
        return self.command_client.send("nod", payload=payload)

    def gaze(self, target: str = "user", duration_ms: int = 1800, mode: str = "smooth") -> CommandResponse:
        """注视控制。"""
        payload = {
            "target": target,
            "duration_ms": self._clamp(int(duration_ms), 100, 10000),
            "mode": mode,
        }
        return self.command_client.send("gaze", payload=payload)

    def gesture(self, name: str, intensity: str = "low") -> CommandResponse:
        """预定义手势动作。"""
        payload = {"name": name, "intensity": intensity}
        return self.command_client.send("gesture", payload=payload)

    def perform_sequence(self, steps: List[Dict[str, Any]], stop_on_error: bool = True) -> CommandResponse:
        """执行复合动作序列。"""
        payload = {"steps": steps, "stop_on_error": bool(stop_on_error)}
        return self.command_client.send("perform_sequence", payload=payload)

    # ------------------------
    # Python2 legacy 动作兼容（按需使用）
    # ------------------------
    def shake_head(self) -> CommandResponse:
        """兼容旧动作：摇头。"""
        return self.command_client.send("shake_head", payload={})

    def stare(self) -> CommandResponse:
        """兼容旧动作：压迫性凝视。"""
        return self.command_client.send("stare", payload={})

    def avert_gaze(self) -> CommandResponse:
        """兼容旧动作：回避视线。"""
        return self.command_client.send("avert_gaze", payload={})

    def reset_gaze(self) -> CommandResponse:
        """兼容旧动作：重置视线。"""
        return self.command_client.send("reset_gaze", payload={})

    def rest(self) -> CommandResponse:
        """兼容旧动作：进入休息姿态。"""
        return self.command_client.send("rest", payload={})

    # ------------------------
    # 内部工具
    # ------------------------
    @staticmethod
    def _clamp(value: int, min_value: int, max_value: int) -> int:
        return max(min_value, min(max_value, value))

    def _local_invalid_payload(self, message: str) -> CommandResponse:
        """构造本地参数错误响应，避免把无效请求发送到服务端。"""
        return self.command_client.local_error_response(
            error_code="E103",
            message="invalid_payload_%s" % message,
        )
