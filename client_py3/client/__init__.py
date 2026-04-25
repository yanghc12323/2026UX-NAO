"""Python3 客户端骨架包。

该包用于对接《通信协议 v1》，作为决策层（Python3）与 NAO 执行层（Python2 Server）之间的
清晰接口层，核心目标是：

1. 统一命令请求/响应结构；
2. 将错误处理与重试策略模块化；
3. 提供高层动作 API，减少业务层直接拼装协议细节。
"""

from .config import ClientConfig, SessionContext
from .models import CommandRequest, CommandResponse
from .command_client import CommandClient
from .mock_client import MockCommandClient
from .action_adapter import RobotActionAdapter
from .error_policy import ErrorPolicy
from .session_flow import InterviewSessionRunner, QuestionProvider, FeedbackProvider
from .interview_policy import InterviewPolicy
from .llm_provider import LLMClient, LLMConfig
from .llm_interview_provider import LLMQuestionProvider, LLMFeedbackProvider

__all__ = [
    "ClientConfig",
    "SessionContext",
    "CommandRequest",
    "CommandResponse",
    "CommandClient",
    "MockCommandClient",
    "RobotActionAdapter",
    "ErrorPolicy",
    "InterviewSessionRunner",
    "QuestionProvider",
    "FeedbackProvider",
    "InterviewPolicy",
    "LLMClient",
    "LLMConfig",
    "LLMQuestionProvider",
    "LLMFeedbackProvider",
]
