"""Unified async streaming LLM adapter.

Single entry point used by zeno-agent-core. Picks a provider based on the
model string: ``mock`` (or empty) uses the offline mock; anything else is
routed through litellm.
"""

from __future__ import annotations

from typing import Any, AsyncIterator

from .providers import mock as _mock
from .providers import litellm_provider as _litellm


def list_providers() -> list[str]:
    return ["mock", "litellm"]


class LLMAdapter:
    def __init__(self, model: str = "mock", **opts: Any) -> None:
        self.model = model or "mock"
        self.opts = opts

    @property
    def is_mock(self) -> bool:
        return self.model == "mock" or self.model.startswith("mock/")

    async def run(
        self,
        prompt: str,
        messages: list[dict],
        tools: list[dict] | None = None,
        stream: bool = True,
    ) -> AsyncIterator[dict]:
        """Stream structured events for one model turn.

        Yields dicts of the form:
            {type:"text_delta", content:str}
            {type:"tool_call", id:str, name:str, args:dict}
            {type:"stop", reason:str}
        """
        tools = tools or []
        if self.is_mock:
            async for event in _mock.run(prompt, messages, tools, stream):
                yield event
            return

        async for event in _litellm.run(
            prompt, messages, tools, stream, model=self.model, **self.opts
        ):
            yield event
