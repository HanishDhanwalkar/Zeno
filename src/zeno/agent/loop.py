from __future__ import annotations

import json
import re
from typing import Any, Callable
from uuid import uuid4

from zeno.agent.prompts import BASE_SYSTEM_PROMPT
from zeno.agent.utils.stream_handler import AnswerStreamHandler


class AgentRunError(RuntimeError):
    """Raised when the model cannot complete a turn.."""


class AgentLoop:
    def __init__(
        self,
        client: Any | None,
        model: str,
        on_message: Any | None = None,
        on_token: Callable[[str], None] | None = None,
    ) -> None:
        if not model:
            raise ValueError("Model must not be empty")

        self.client = client
        self.model = model
        self.on_message = on_message
        self.on_token = on_token

        self.messages: list[dict[str, Any]] = []
        self._history: list[Any] = []
        self._agent: Any | None = None

    def run_turn(self, prompt: str) -> str:
        if not prompt.strip():
            raise ValueError("Prompt must not be empty")

        self.ensure_agent()

        previous_message_count = len(self._history)
        agent = self._agent

        result: dict[str, Any] | None = None

        stream_loop = self
        stream_handler = AnswerStreamHandler(stream_loop)

        try:
            for mode, chunk in agent.stream(
                {
                    "messages": [
                        *self._history, {"role": "user", "content": prompt}
                    ],
                },
                config={"callbacks": [stream_handler]},
                stream_mode=["messages", "values"]
            ):
                if mode == "messages":
                    continue

                if mode != "values":
                    continue

                result = chunk

        except Exception as e:
            raise AgentRunError(
                f"Agent failed to complete turn: {e}"
            ) from e

        if result is None:
            raise AgentRunError(
                "Agent failed to complete turn: no agent state returned"
            )
        history = result.get("messages")
        if not isinstance(history, list) or len(history) <= previous_message_count:
            raise AgentRunError(
                "Agent failed to complete turn: no messages returned"
            )
        self._history = history

        new_messages = [
            self._message_dict(message)
            for message in history[previous_message_count:]
        ]

        for message in new_messages:
            self.messages.append(message)
            if self.on_message is not None:
                self.on_message(message)

        for message in reversed(new_messages):
            if message.get("role") == "assistant" and not message.get("tool_calls"):
                content = message.get("content")
                text = "".join(self._content_text_tokens(content))
                if text.strip():
                    return text

        raise AgentRunError(
            "Agent failed to complete turn: no final assistant message returned"
        )

    def clear_context(self) -> dict[str, Any]:
        self._history.clear()
        self.messages.clear()

        clear_event = {
            "role": "system",
            "content": "Context cleared.",
            "event": "clear_context",
        }
        if self.on_message is not None:
            self.on_message(clear_event)

        return clear_event

    def ensure_agent(self) -> None:
        if self._agent is not None:
            return

        # TODO
        pass

    @staticmethod
    def _content_text_tokens(content: str) -> list[str]:
        if isinstance(content, str):
            return [content] if content.strip() else []

        if isinstance(content, list):
            return [
                block
                if isinstance(block, str)
                else block.get("text")
                for block in content
                if isinstance(block, str) or (isinstance(block, dict) and isinstance(block.get("text"), str))
            ]

        return []

    @staticmethod
    def _message_dict(message: Any) -> dict[str, Any]:
        if isinstance(message, dict):
            return message

        message_type = getattr(message, "type", "")
        role = {"human": "user", "ai": "assistant"}.get(
            message_type, message_type)
        record: dict[str, Any] = {
            "role": role,
            "content": getattr(message, "content", ""),
        }
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            record["tool_calls"] = [
                {
                    "type": "function",
                    "function": {
                        "name": call["name"],
                        "arguments": call["args"],

                    }
                }
                for call in tool_calls
            ]

        if role == "tool":
            record["role"] = getattr(message, "name", "")

        return record
