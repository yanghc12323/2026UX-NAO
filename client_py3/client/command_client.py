"""命令客户端实现。

该模块负责：
1. 构造协议请求（自动注入 request_id/timestamp/session 元数据）；
2. 发送 HTTP JSON 请求到 Python2 NAO Server；
3. 解析响应并执行重试策略。
"""

import json
import uuid
from typing import Any, Dict, Optional
from urllib import request, error

from .config import ClientConfig, SessionContext
from .error_policy import ErrorPolicy
from .models import CommandRequest, CommandResponse


class CommandClient(object):
    """协议命令客户端。

    说明：
    - 当前默认使用 HTTP POST（`application/json`）发送到 `config.server_url`。
    - 若后续需要 TCP 或 WebSocket，可在该类外新增传输适配器并复用本类请求构造逻辑。
    """

    def __init__(
        self,
        config: ClientConfig,
        session: SessionContext,
        error_policy: Optional[ErrorPolicy] = None,
    ):
        self.config = config
        self.session = session
        self.error_policy = error_policy or ErrorPolicy()

    def build_request(
        self,
        command: str,
        payload: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        retry_count: int = 0,
        turn_id: Optional[str] = None,
    ) -> CommandRequest:
        """构造单条命令请求。"""
        req_timeout = int(timeout_ms or self.config.default_timeout_ms)
        req_turn_id = turn_id or self.session.next_turn_id()
        return CommandRequest(
            protocol_version=self.config.protocol_version,
            request_id=self._new_request_id(),
            timestamp_ms=CommandRequest.now_ms(),
            session_id=self.session.session_id,
            participant_id=self.session.participant_id,
            condition_id=self.session.condition_id,
            turn_id=req_turn_id,
            command=command,
            payload=payload,
            timeout_ms=req_timeout,
            retry_count=retry_count,
        )

    def send(
        self,
        command: str,
        payload: Dict[str, Any],
        timeout_ms: Optional[int] = None,
        turn_id: Optional[str] = None,
    ) -> CommandResponse:
        """发送命令并按策略重试。

        返回：
            `CommandResponse`（无论成功失败都返回结构化对象）。
        """
        max_retry = max(0, int(self.config.max_retry))
        last_response = None

        for retry in range(max_retry + 1):
            req = self.build_request(
                command=command,
                payload=payload,
                timeout_ms=timeout_ms,
                retry_count=retry,
                turn_id=turn_id,
            )

            response = self._send_once(req)
            last_response = response

            if response.is_ok:
                return response

            if retry >= max_retry:
                return response

            if not self.error_policy.is_retryable(response.error_code):
                return response

        # 理论上不会走到这里，保底返回最后一次结果
        return last_response or self._build_internal_error_response("", "E500", "unknown")

    def _send_once(self, req_obj: CommandRequest) -> CommandResponse:
        """执行单次 HTTP 发送。"""
        data = json.dumps(req_obj.to_dict(), ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url=self.config.server_url,
            data=data,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        timeout_s = self._resolve_http_timeout(req_obj.timeout_ms)

        try:
            with request.urlopen(req, timeout=timeout_s) as resp:
                raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            return CommandResponse.from_dict(parsed)
        except error.HTTPError as e:
            return self._build_internal_error_response(
                request_id=req_obj.request_id,
                error_code="E500",
                message="http_error_%s" % e.code,
            )
        except error.URLError:
            return self._build_internal_error_response(
                request_id=req_obj.request_id,
                error_code="E200",
                message="robot_disconnected_or_server_unreachable",
            )
        except ValueError:
            return self._build_internal_error_response(
                request_id=req_obj.request_id,
                error_code="E100",
                message="invalid_json_response",
            )
        except Exception as exc:  # noqa: BLE001
            return self._build_internal_error_response(
                request_id=req_obj.request_id,
                error_code="E500",
                message="internal_exception_%s" % exc.__class__.__name__,
            )

    def _resolve_http_timeout(self, request_timeout_ms: int) -> float:
        """将协议毫秒超时映射为 HTTP 层秒超时。"""
        request_timeout_s = max(0.1, float(request_timeout_ms) / 1000.0)
        base_timeout_s = float(self.config.connect_timeout_s) + float(self.config.read_timeout_s)
        return max(request_timeout_s, base_timeout_s)

    def _new_request_id(self) -> str:
        """生成唯一 request_id。"""
        return "REQ_%s" % uuid.uuid4().hex[:16]

    def _build_internal_error_response(self, request_id: str, error_code: str, message: str) -> CommandResponse:
        """构造客户端本地错误响应。"""
        return CommandResponse(
            protocol_version=self.config.protocol_version,
            request_id=request_id,
            server_timestamp_ms=CommandRequest.now_ms(),
            status="error",
            error_code=error_code,
            message=message,
            result={},
        )

    def local_error_response(self, error_code: str, message: str) -> CommandResponse:
        """暴露给上层模块的本地错误构造接口。

        场景：
        - 上层在发送前完成参数校验；
        - 命中参数错误时，不进入网络调用，直接返回标准结构。
        """
        return self._build_internal_error_response(request_id="", error_code=error_code, message=message)
