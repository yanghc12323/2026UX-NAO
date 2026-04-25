"""配置与会话上下文定义。

该模块集中管理：
1. 客户端运行参数（服务端地址、超时、重试等）；
2. 会话元数据（session_id / participant_id / condition_id）；
3. turn_id 生成策略。
"""

from dataclasses import dataclass, field


@dataclass
class ClientConfig:
    """命令客户端配置。"""

    server_url: str = "http://127.0.0.1:8000/command"
    protocol_version: str = "1.0"
    default_timeout_ms: int = 5000
    connect_timeout_s: float = 2.0
    read_timeout_s: float = 6.0
    max_retry: int = 1


@dataclass
class SessionContext:
    """会话上下文（用于自动注入请求字段）。"""

    session_id: str
    participant_id: str
    condition_id: str
    turn_prefix: str = "T"
    _turn_counter: int = field(default=0, init=False, repr=False)

    def next_turn_id(self) -> str:
        """生成并返回下一轮 turn_id，如 `T001`。"""
        self._turn_counter += 1
        return "%s%03d" % (self.turn_prefix, self._turn_counter)
