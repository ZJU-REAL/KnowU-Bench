import time
from collections.abc import Mapping
from http import HTTPStatus
from typing import Any

from loguru import logger

try:
    import dashscope
    from dashscope import MultiModalConversation
except ImportError:  # pragma: no cover - depends on local environment
    dashscope = None
    MultiModalConversation = None

from knowu_bench.agents.base import MCPAgent
from knowu_bench.agents.implementations.qwen3_5 import Qwen3_5AgentMCP


class Qwen36PlusAgentMCP(Qwen3_5AgentMCP):
    """Dedicated Qwen3.6-plus agent backed by the DashScope SDK."""

    def __init__(
        self,
        model_name: str,
        llm_base_url: str,
        api_key: str = "empty",
        observation_type: str = "screenshot",
        runtime_conf: dict[str, Any] | None = None,
        *args: Any,
        **kwargs: Any,
    ):
        MCPAgent.__init__(self, *args, **kwargs)
        self.model_name = model_name
        self.llm_base_url = llm_base_url
        self.dashscope_base_url = self._normalize_dashscope_base_url(llm_base_url)
        self.api_key = api_key
        self.observation_type = observation_type
        self.runtime_conf = {"temperature": 0.0, **(runtime_conf or {})}

        self.thoughts = []
        self.actions = []
        self.conclusions = []
        self.history_images = []
        self.history_responses = []

    @staticmethod
    def _normalize_dashscope_base_url(base_url: str) -> str:
        normalized = (base_url or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
        suffix = "/compatible-mode/v1"
        if normalized.endswith(suffix):
            return f"{normalized[:-len(suffix)]}/api/v1"
        return normalized

    @staticmethod
    def _read_field(obj: Any, key: str, default: Any = None) -> Any:
        if isinstance(obj, Mapping):
            return obj.get(key, default)
        return getattr(obj, key, default)

    @classmethod
    def _extract_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, Mapping):
            return str(content.get("text", "")).strip()
        if isinstance(content, list):
            text_parts: list[str] = []
            for item in content:
                text = cls._extract_text(item)
                if text:
                    text_parts.append(text)
            return "\n".join(text_parts).strip()
        text = cls._read_field(content, "text")
        if text is not None:
            return str(text).strip()
        return str(content or "").strip()

    def _to_dashscope_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted_messages: list[dict[str, Any]] = []
        for message in messages:
            content = message.get("content", [])
            if isinstance(content, str):
                converted_content = [{"text": content}]
            else:
                converted_content = []
                for item in content:
                    if not isinstance(item, Mapping):
                        converted_content.append({"text": str(item)})
                        continue

                    item_type = item.get("type")
                    if item_type == "text":
                        converted_content.append({"text": item.get("text", "")})
                    elif item_type == "image_url":
                        image_url = item.get("image_url", {})
                        if isinstance(image_url, Mapping):
                            converted_content.append({"image": image_url.get("url", "")})
                    else:
                        text = item.get("text")
                        if text is not None:
                            converted_content.append({"text": str(text)})

            converted_messages.append(
                {
                    "role": message.get("role", "user"),
                    "content": converted_content,
                }
            )
        return converted_messages

    def _build_request_kwargs(self) -> dict[str, Any]:
        supported_keys = {"temperature", "top_p", "max_tokens", "seed"}
        return {
            key: value
            for key, value in self.runtime_conf.items()
            if key in supported_keys and value is not None
        }

    def _log_dashscope_usage(self, response: Any) -> None:
        usage = self._read_field(response, "usage")
        if usage is None:
            return

        prompt_tokens = self._read_field(usage, "input_tokens", 0)
        if not prompt_tokens:
            prompt_tokens = self._read_field(usage, "prompt_tokens", 0)

        completion_tokens = self._read_field(usage, "output_tokens", 0)
        if not completion_tokens:
            completion_tokens = self._read_field(usage, "completion_tokens", 0)

        self._total_prompt_tokens += int(prompt_tokens or 0)
        self._total_completion_tokens += int(completion_tokens or 0)

        logger.debug(
            "DashScope usage: completion={}, prompt={} | Total: completion={}, prompt={}",
            completion_tokens,
            prompt_tokens,
            self._total_completion_tokens,
            self._total_prompt_tokens,
        )

    def openai_chat_completions_create(
        self,
        model: str,
        messages: list[dict],
        retry_times: int = 3,
        stream: bool = False,
        **kwargs: Any,
    ) -> str | None:
        del stream

        if dashscope is None or MultiModalConversation is None:
            raise ImportError(
                "dashscope is required for agent_type=qwen3_6_plus. "
                "Install it with `pip install dashscope` or `uv sync`."
            )

        self._last_openai_error = None

        while retry_times > 0:
            try:
                dashscope.base_http_api_url = self.dashscope_base_url
                response = MultiModalConversation.call(
                    api_key=self.api_key if self.api_key else None,
                    model=model,
                    messages=self._to_dashscope_messages(messages),
                    **kwargs,
                )

                status_code = self._read_field(response, "status_code")
                status_value = int(status_code) if status_code is not None else HTTPStatus.OK
                if status_value != HTTPStatus.OK:
                    code = self._read_field(response, "code", "unknown_error")
                    message = self._read_field(response, "message", "unknown error")
                    self._last_openai_error = (
                        f"DashScopeError status={status_value} code={code}: {message}"
                    )
                    logger.warning("Error calling DashScope API: {}", self._last_openai_error)
                    retry_times -= 1
                    time.sleep(1)
                    continue

                output = self._read_field(response, "output")
                choices = self._read_field(output, "choices", [])
                if not choices:
                    self._last_openai_error = "DashScope returned no choices"
                    logger.warning(self._last_openai_error)
                    retry_times -= 1
                    time.sleep(1)
                    continue

                message = self._read_field(choices[0], "message")
                content = self._read_field(message, "content")
                final_content = self._extract_text(content)
                if not final_content:
                    self._last_openai_error = "DashScope returned empty content"
                    logger.warning(self._last_openai_error)
                    retry_times -= 1
                    time.sleep(1)
                    continue

                self._log_dashscope_usage(response)
                self._last_openai_error = None
                return final_content
            except Exception as e:
                self._last_openai_error = f"{type(e).__name__}: {e}"
                logger.warning("Error calling DashScope SDK: {}", e)
                retry_times -= 1
                time.sleep(1)

        return None
