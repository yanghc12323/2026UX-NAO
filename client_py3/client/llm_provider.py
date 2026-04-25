"""DeepSeek LLM 调用封装（OpenAI Compatible Chat Completions）。

设计原则：
- 对上层暴露稳定接口 `chat_completion_text`；
- 将网络细节、超时、错误处理封装在模块内部；
- 无 API key 时由上层决定是否回退到 demo provider。
"""

import json
from dataclasses import dataclass
from typing import Any, Dict, List
from urllib import request, error


@dataclass
class LLMConfig:
    """LLM 请求配置。"""

    api_key: str
    model: str = "deepseek-chat"
    base_url: str = "https://api.deepseek.com/chat/completions"
    timeout_s: float = 20.0
    temperature: float = 0.7
    max_tokens: int = 512


class LLMClient(object):
    """最小可维护 LLM 客户端。"""

    def __init__(self, config: LLMConfig):
        self.config = config

    def chat_completion_text(self, system_prompt: str, user_prompt: str) -> str:
        """调用 chat completions 并返回首条文本。"""
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": float(self.config.temperature),
            "max_tokens": int(self.config.max_tokens),
        }

        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            url=self.config.base_url,
            data=data,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": "Bearer %s" % self.config.api_key,
            },
            method="POST",
        )

        try:
            with request.urlopen(req, timeout=float(self.config.timeout_s)) as resp:
                raw = resp.read().decode("utf-8")
            parsed = json.loads(raw)
            return self._extract_text(parsed)
        except error.HTTPError as exc:
            raise RuntimeError("llm_http_error_%s" % exc.code)
        except error.URLError:
            raise RuntimeError("llm_network_unreachable")
        except ValueError:
            raise RuntimeError("llm_invalid_json")
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("llm_internal_exception_%s" % exc.__class__.__name__)

    def _extract_text(self, response_data: Dict[str, Any]) -> str:
        """从 OpenAI compatible 返回体提取文本。"""
        choices = response_data.get("choices", [])
        if not isinstance(choices, list) or not choices:
            raise RuntimeError("llm_empty_choices")

        first = choices[0] or {}
        message = first.get("message", {}) if isinstance(first, dict) else {}
        content = message.get("content", "") if isinstance(message, dict) else ""

        # 兼容 content 是字符串或结构化数组两种返回。
        if isinstance(content, str):
            text = content.strip()
            if text:
                return text

        if isinstance(content, list):
            chunks: List[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    chunks.append(str(item.get("text", "")))
            text = "\n".join([c for c in chunks if c.strip()]).strip()
            if text:
                return text

        raise RuntimeError("llm_empty_content")
