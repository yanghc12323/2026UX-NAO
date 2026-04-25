"""本地联调用 Mock 客户端。

该客户端不访问真实 NAO Server，而是直接返回成功响应，
用于在没有机器人设备时调试 Python3 流程层代码。
"""

from typing import Any, Dict, Optional

from .command_client import CommandClient
from .models import CommandResponse, CommandRequest


class MockCommandClient(CommandClient):
    """用于本地开发测试的命令客户端。"""

    def send(
        self,
        command: str,
        payload: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        turn_id: Optional[str] = None,
    ) -> CommandResponse:
        req = self.build_request(command=command, payload=payload, timeout_ms=timeout_ms, turn_id=turn_id)
        return CommandResponse(
            protocol_version=self.config.protocol_version,
            request_id=req.request_id,
            server_timestamp_ms=CommandRequest.now_ms(),
            status="ok",
            error_code="E000",
            message="mock_success",
            result={
                "execution_ms": 1,
                "robot_state": "idle",
                "mock_command": command,
                "mock_payload": payload,
            },
        )
