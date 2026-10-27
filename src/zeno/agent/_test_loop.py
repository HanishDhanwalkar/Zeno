"""No-LLM runtime test loop for Zeno Agent.

Executes and logs the complete lifecycle and function call sequence of AgentLoop
without making external LLM API calls:
  1. User calls AgentLoop.run_turn(prompt)
  2. AgentLoop calls ensure_agent()
  3. AnswerStreamHandler initialized with ToolRegistry definitions
  4. AgentLoop invokes agent.stream()
  5. Streaming tokens emitted via AnswerStreamHandler -> on_token()
  6. Tool calls detected via tool_call_chunks (stream suppressed)
  7. Final state received from stream mode 'values'
  8. New messages normalized through _message_dict()
  9. on_message() callbacks dispatched for each new message
 10. Final assistant response text returned to user
 11. clear_context() resets conversation state
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure 'src' is in sys.path when running directly
src_dir = Path(__file__).resolve().parent.parent.parent
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))

from langchain_core.messages import AIMessage, ToolMessage
from zeno.agent.loop import AgentLoop, AgentRunError
from zeno.agent.utils.stream_handler import AnswerStreamHandler
from zeno.tools.registry import ToolRegistry


class CallTracer:
    """Records and prints chronological function call sequences."""

    def __init__(self, suite_name: str) -> None:
        self.suite_name = suite_name
        self.calls: list[str] = []

    def log(self, caller: str, action: str, details: str = "") -> None:
        step = len(self.calls) + 1
        msg = f"Step {step:02d} | [{caller}] -> {action}"
        if details:
            msg += f" ({details})"
        self.calls.append(msg)
        print(f"  {msg}")

    def print_summary(self) -> None:
        border = "=" * 80
        print(f"\n{border}")
        print(f"EXECUTION CALL ORDER SUMMARY: {self.suite_name}")
        print(border)
        for call in self.calls:
            print(f"  {call}")
        print(f"{border}\n")


class MockToolRegistry(ToolRegistry):
    """Tool registry pre-configured with mock tool definitions."""

    def __init__(self, tracer: CallTracer) -> None:
        super().__init__()
        self.tracer = tracer
        self.tracer.log("MockToolRegistry", "__init__", "Initializing tool definitions")
        self.definitions = [
            {"functions": {"name": "bash", "description": "Execute bash commands"}},
            {"functions": {"name": "read_file", "description": "Read file contents"}},
        ]


class MockChunk:
    """Simulates a chunk object containing message chunks and tool calls."""

    def __init__(self, content: str = "", tool_call_chunks: list[dict[str, Any]] | None = None) -> None:
        class InnerMessage:
            def __init__(self, content: str, tool_chunks: list[dict[str, Any]] | None):
                self.content = content
                self.tool_call_chunks = tool_chunks or []

        self.message = InnerMessage(content, tool_call_chunks)


class MockAgent:
    """Simulates LangChain / LangGraph agent execution without an external LLM."""

    def __init__(self, tracer: CallTracer, scenario: str = "text") -> None:
        self.tracer = tracer
        self.scenario = scenario

    def stream(
        self,
        inputs: dict[str, Any],
        config: dict[str, Any] | None = None,
        stream_mode: list[str] | None = None,
    ):
        self.tracer.log("MockAgent", "stream", f"Started stream with mode={stream_mode}")
        callbacks = (config or {}).get("callbacks", [])
        stream_handler = callbacks[0] if callbacks else None

        if self.scenario == "text":
            # Scenario 1: Standard token-by-token streaming
            tokens = ["Hello", " ", "developer", "!", " I", " can", " help", " you."]
            if stream_handler:
                self.tracer.log("AnswerStreamHandler", "on_model_start", "Resetting stream buffer")
                stream_handler.on_model_start()

                for token in tokens:
                    chunk = MockChunk(content=token)
                    self.tracer.log("AnswerStreamHandler", "on_llm_new_token", f"token='{token}'")
                    stream_handler.on_llm_new_token(token, chunk)

            # Yield intermediate messages chunk
            self.tracer.log("MockAgent", "yield ('messages')", "Emitting intermediate message chunk")
            yield ("messages", {"role": "assistant", "content": "".join(tokens)})

            # Yield final state values
            final_messages = [
                *inputs.get("messages", []),
                {"role": "assistant", "content": "".join(tokens)},
            ]
            self.tracer.log("MockAgent", "yield ('values')", f"Emitting final state with {len(final_messages)} messages")
            yield ("values", {"messages": final_messages})

        elif self.scenario == "tool_call":
            # Scenario 2: Agent issues a tool call, suppressing user stream
            if stream_handler:
                self.tracer.log("AnswerStreamHandler", "on_model_start", "Resetting stream buffer")
                stream_handler.on_model_start()

                tool_chunk = MockChunk(
                    content="",
                    tool_call_chunks=[{"name": "read_file", "args": '{"path": "src/main.py"}'}],
                )
                self.tracer.log(
                    "AnswerStreamHandler",
                    "on_llm_new_token",
                    "Detected tool_call_chunks -> Suppressing stream_toolcall=True",
                )
                stream_handler.on_llm_new_token("", tool_chunk)

            # Yield final values including assistant tool call, tool response, and final assistant message
            assistant_tool_msg = AIMessage(
                content="",
                tool_calls=[{"name": "read_file", "args": {"path": "src/main.py"}, "id": "call_1"}],
            )
            tool_result_msg = ToolMessage(
                name="read_file",
                content="def main(): print('Hello World')",
                tool_call_id="call_1",
            )
            final_assistant_msg = AIMessage(
                content="I examined src/main.py: it defines the main() entrypoint.",
            )

            final_messages = [
                *inputs.get("messages", []),
                assistant_tool_msg,
                tool_result_msg,
                final_assistant_msg,
            ]
            self.tracer.log("MockAgent", "yield ('values')", f"Emitting final state with {len(final_messages)} messages")
            yield ("values", {"messages": final_messages})


class TracedAgentLoop(AgentLoop):
    """Subclass of AgentLoop instrumented with tracing for all key hooks."""

    def __init__(
        self,
        client: Any | None,
        tools: ToolRegistry,
        model: str,
        tracer: CallTracer,
        scenario: str = "text",
        on_message: Any | None = None,
        on_token: Any | None = None,
    ) -> None:
        self.tracer = tracer
        self.scenario = scenario
        self.tracer.log("TracedAgentLoop", "__init__", f"model='{model}'")
        super().__init__(
            client=client,
            tools=tools,
            model=model,
            on_message=on_message,
            on_token=on_token,
        )

    def ensure_agent(self) -> None:
        self.tracer.log("TracedAgentLoop", "ensure_agent", "Verifying or building agent")
        if self._agent is None:
            self.tracer.log("TracedAgentLoop", "ensure_agent", "Created MockAgent")
            self._agent = MockAgent(self.tracer, scenario=self.scenario)

    def run_turn(self, prompt: str) -> str:
        self.tracer.log("TracedAgentLoop", "run_turn", f"Called with prompt='{prompt}'")
        result = super().run_turn(prompt)
        self.tracer.log("TracedAgentLoop", "run_turn", f"Turn completed successfully, returning: '{result}'")
        return result

    @staticmethod
    def _message_dict(message: Any) -> dict[str, Any]:
        result = AgentLoop._message_dict(message)
        return result

    def clear_context(self) -> dict[str, Any]:
        self.tracer.log("TracedAgentLoop", "clear_context", "Clearing history and active messages")
        result = super().clear_context()
        self.tracer.log("TracedAgentLoop", "clear_context", "Emitted clear_context event")
        return result


def test_standard_text_turn() -> None:
    """Test 1: Standard text generation with live token streaming."""
    tracer = CallTracer("TEST 1: Standard Turn with Live Token Streaming")
    print(f"\n--- Starting {tracer.suite_name} ---")

    tokens_received: list[str] = []
    messages_received: list[dict[str, Any]] = []

    def on_token(t: str) -> None:
        tracer.log("UserCallback", "on_token", f"Received streamed token: '{t}'")
        tokens_received.append(t)

    def on_message(m: dict[str, Any]) -> None:
        tracer.log("UserCallback", "on_message", f"Received message role='{m.get('role')}'")
        messages_received.append(m)

    tools = MockToolRegistry(tracer)
    loop = TracedAgentLoop(
        client=None,
        tools=tools,
        model="mock-gpt-4o",
        tracer=tracer,
        scenario="text",
        on_message=on_message,
        on_token=on_token,
    )

    answer = loop.run_turn("Hello, can you help me?")

    assert answer == "Hello developer! I can help you.", f"Unexpected answer: {answer}"
    assert len(tokens_received) > 0, "No tokens were streamed!"
    assert len(messages_received) == 2, f"Expected 2 messages (user + assistant), got {len(messages_received)}"
    assert loop.messages[0]["role"] == "user"
    assert loop.messages[1]["role"] == "assistant"
    assert loop.messages[1]["content"] == answer

    tracer.print_summary()
    print("Test 1 PASSED: Text turn and token streaming executed in correct order.\n")


def test_tool_call_turn() -> None:
    """Test 2: Tool call turn suppressing token stream, followed by final answer."""
    tracer = CallTracer("TEST 2: Tool Execution with Stream Suppression")
    print(f"\n--- Starting {tracer.suite_name} ---")

    tokens_received: list[str] = []
    messages_received: list[dict[str, Any]] = []

    def on_token(t: str) -> None:
        tracer.log("UserCallback", "on_token", f"Streamed token: '{t}'")
        tokens_received.append(t)

    def on_message(m: dict[str, Any]) -> None:
        tracer.log("UserCallback", "on_message", f"Received message role='{m.get('role')}'")
        messages_received.append(m)

    tools = MockToolRegistry(tracer)
    loop = TracedAgentLoop(
        client=None,
        tools=tools,
        model="mock-gpt-4o",
        tracer=tracer,
        scenario="tool_call",
        on_message=on_message,
        on_token=on_token,
    )

    answer = loop.run_turn("What does src/main.py contain?")

    assert "src/main.py" in answer, f"Unexpected answer: {answer}"
    assert len(tokens_received) == 0, "Tokens should have been suppressed during tool call!"
    assert len(messages_received) == 4, f"Expected 4 new messages (user, tool call, tool output, assistant), got {len(messages_received)}"

    # Check normalized roles
    roles = [m["role"] for m in messages_received]
    assert roles == ["user", "assistant", "read_file", "assistant"], f"Unexpected roles: {roles}"

    tracer.print_summary()
    print("Test 2 PASSED: Tool call detected, streaming suppressed, and final answer returned.\n")


def test_clear_context() -> None:
    """Test 3: Clearing context and history."""
    tracer = CallTracer("TEST 3: Clear Context Reset")
    print(f"\n--- Starting {tracer.suite_name} ---")

    events: list[dict[str, Any]] = []

    def on_message(event: dict[str, Any]) -> None:
        tracer.log("UserCallback", "on_message", f"Event: {event.get('event')}")
        events.append(event)

    tools = MockToolRegistry(tracer)
    loop = TracedAgentLoop(
        client=None,
        tools=tools,
        model="mock-gpt-4o",
        tracer=tracer,
        scenario="text",
        on_message=on_message,
    )

    # Run turn first
    loop.run_turn("Initial prompt")
    assert len(loop.messages) > 0
    assert len(loop._history) > 0

    # Clear context
    clear_event = loop.clear_context()

    assert len(loop.messages) == 0, "messages list should be empty after clear"
    assert len(loop._history) == 0, "_history list should be empty after clear"
    assert clear_event["event"] == "clear_context"
    assert len(events) >= 2  # Turn message + clear event

    tracer.print_summary()
    print("Test 3 PASSED: Context successfully cleared.\n")


def test_error_handling() -> None:
    """Test 4: Error handling for empty prompts and failed turns."""
    tracer = CallTracer("TEST 4: Input Validation & Agent Error Handling")
    print(f"\n--- Starting {tracer.suite_name} ---")

    tools = MockToolRegistry(tracer)
    loop = TracedAgentLoop(
        client=None,
        tools=tools,
        model="mock-gpt-4o",
        tracer=tracer,
    )

    # 1. Empty prompt check
    tracer.log("TestRunner", "assert_raises", "Calling run_turn with empty prompt ''")
    try:
        loop.run_turn("   ")
        raise AssertionError("Expected ValueError for empty prompt")
    except ValueError as e:
        tracer.log("TracedAgentLoop", "ValueError", f"Caught expected error: {e}")

    # 2. Agent failure check
    class BrokenAgent:
        def stream(self, *args, **kwargs):
            raise RuntimeError("Underlying LLM service unavailable")

    tracer.log("TestRunner", "assert_raises", "Calling run_turn with failing agent")
    loop._agent = BrokenAgent()
    try:
        loop.run_turn("This will fail")
        raise AssertionError("Expected AgentRunError")
    except AgentRunError as e:
        tracer.log("TracedAgentLoop", "AgentRunError", f"Caught expected error: {e}")

    tracer.print_summary()
    print("Test 4 PASSED: Expected errors caught and handled properly.\n")


def run_all_tests() -> None:
    print("\n" + "#" * 80)
    print("RUNNING ZENO AGENT NO-LLM RUNTIME TEST SUITE")
    print("#" * 80)

    test_standard_text_turn()
    test_tool_call_turn()
    test_clear_context()
    test_error_handling()

    print("#" * 80)
    print("ALL 4 TESTS COMPLETED SUCCESSFULLY!")
    print("#" * 80 + "\n")


if __name__ == "__main__":
    run_all_tests()
