"""协议模型定义（与 docs/communication_protocol_v1.md 对齐）。"""

from dataclasses import dataclass, field
from typing import Any, Dict
import time


@dataclass
class CommandRequest:
    """客户端命令请求。

    该结构对应协议中的请求报文字段，`to_dict` 后可直接发送给 NAO Server。
    """

    protocol_version: str
    request_id: str
    timestamp_ms: int
    session_id: str
    participant_id: str
    condition_id: str
    turn_id: str
    command: str
    payload: Dict[str, Any]
    timeout_ms: int
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        """转换为可序列化字典。"""
        return {
            "protocol_version": self.protocol_version,
            "request_id": self.request_id,
            "timestamp_ms": self.timestamp_ms,
            "session_id": self.session_id,
            "participant_id": self.participant_id,
            "condition_id": self.condition_id,
            "turn_id": self.turn_id,
            "command": self.command,
            "payload": self.payload,
            "timeout_ms": self.timeout_ms,
            "retry_count": self.retry_count,
        }

    @classmethod
    def now_ms(cls) -> int:
        """返回当前 Unix 毫秒时间戳。"""
        return int(time.time() * 1000)


@dataclass
class CommandResponse:
    """服务端响应模型。"""

    protocol_version: str
    request_id: str
    server_timestamp_ms: int
    status: str
    error_code: str
    message: str
    result: Dict[str, Any] = field(default_factory=dict)

    @property
    def is_ok(self) -> bool:
        """是否执行成功。"""
        return self.status == "ok" and self.error_code == "E000"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "CommandResponse":
        """从字典安全构造响应对象（字段缺失时给默认值）。"""
        return cls(
            protocol_version=str(data.get("protocol_version", "1.0")),
            request_id=str(data.get("request_id", "")),
            server_timestamp_ms=int(data.get("server_timestamp_ms", 0) or 0),
            status=str(data.get("status", "error")),
            error_code=str(data.get("error_code", "E500")),
            message=str(data.get("message", "unknown error")),
            result=dict(data.get("result", {}) or {}),
        )
