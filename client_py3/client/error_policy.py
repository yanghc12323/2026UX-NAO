"""错误策略模块。

职责：
1. 识别可重试错误码；
2. 提供重试决策接口；
3. 提供是否应中止会话的决策接口。
"""

from typing import Set


class ErrorPolicy(object):
    """通信错误策略。"""

    # 按协议文档：E300/E301/E200 可重试
    RETRYABLE_CODES: Set[str] = {"E300", "E301", "E200"}

    # 发生后建议立刻中止会话的严重错误
    FATAL_CODES: Set[str] = {"E500"}

    def is_retryable(self, error_code: str) -> bool:
        """判断错误是否可重试。"""
        return error_code in self.RETRYABLE_CODES

    def should_abort_session(self, error_code: str) -> bool:
        """判断是否建议中止会话。"""
        return error_code in self.FATAL_CODES
