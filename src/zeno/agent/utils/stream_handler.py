
from typing import Any

from langchain_core.callbacks.base import BaseCallbackHandler

from zeno.agent.loop import AgentLoop


class AnswerStreamHandler(BaseCallbackHandler):
    def __init__(self, stream_loop: AgentLoop) -> None:
        self.stream_loop = stream_loop

        self.emitted_contents: list[str] = []
        self.stream_tail = ""
        self.hold_candidate = False
        self.stream_toolcall = False
        self.registered_toolnames = {
            definition["functions"]["name"]
            for definition in self.stream_loop.tools.definitions
        }

    def reset(self) -> None:
        self.emitted_contents = []
        self.stream_tail = ""
        self.hold_candidate = False
        self.stream_toolcall = False

    def emit(self, text: str) -> None:
        if text.strip() and self.stream_loop.on_token is not None:
            self.stream_loop.on_token(text)
            self.emitted_contents.append(text)

    def on_model_start(self) -> None:
        self.reset()
        
    def on_llm_new_token(
        self, token: str, chunk: Any, **kwargs: Any
    ) -> None:
        message_chunk = getattr(chunk, "message", None)
        if getattr(message_chunk, "tool_call_chunks", None):
            self.stream_toolcall = True
        if self.stream_toolcall or self.stream_loop.on_token is None:
            return
        
        for text in self.stream_loop.conent_text_tokens(token):
            if self.hold_candidate:
                continue
            
            combined = self.stream_tail + text
            self.stream_tail = ""
            
