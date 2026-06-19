# Zeno — Ultra-Lean AI Coding Harness

The **simplest and fastest** AI coding tool possible, by shedding all traditional over-engineering (no heavy monorepo setups, no virtual DOM overhead, no heavy database states, and no complex background process management)

> AI coding harness with a minimal, replaceable TUI and exactly four tools.

> 4 distinct packages (`zeno-ai`, `zeno-agent-core`, `zeno-tui`, and `zeno-coding-agent`).

## Core Architecture

- **4 packages:** `zeno-tui`, `zeno-coding-agent` (Node); `zeno-agent-core`, `zeno-ai` (Python).
- **Communication:** long‑running JSON‑RPC 2.0 over stdio (NDJSON), Node spawns Python child process.
- **TUI strategy:** start with **Ink** (React) for fast iteration, wrapped behind a `Renderer` interface so it can be replaced later by an in‑house zero‑dependency renderer.
- **Tools:** only `read`, `write`, `edit`, `bash`. All tool execution happens in Python, but destructive `bash` commands are gated by Node.
- **Context pruning:** performed by `zeno-coding-agent` after every user message; keeps the latest 40k tokens of assistant/tool outputs. (More about `context` in later version)
- **Agent loop:** stateless on Python side; Node sends the full (pruned) message list on every run.

---

## 1. Environment Setup

- [ ] **Node.js project** (`zeno-tui` + `zeno-coding-agent`)
  - Initialize npm package.
  - Install runtime dependencies: `ink`, `react` (for initial TUI).
  - Set up TypeScript config (`tsconfig.json`).

- [ ] **Python environment** (`zeno-agent-core` + `zeno-ai`)
  - Create virtual environment.
  - Add requirements: `pydantic`, `asyncio` (stdlib), `litellm` (or your existing LLM adapter), `tree-sitter` (if needed later).
  - Define package structure: `__init__.py`, `main.py` (entry point for stdio RPC).

- [ ] **Project structure**

```file-structure
z/  
├── packages/  
│ ├── zeno-tui/ # Node  
│ ├── zeno-coding-agent/ # Node  
│ ├── zeno-agent-core/ # Python  
│ └── zeno-ai/ # Python  
├── scripts/  
│ └── start.sh # launches Node (which spawns Python)  
└── docs/  
└── TODO.md
```

## 2. JSON‑RPC Transport Layer

- [ ] **Node side: RPC client**
  - Spawn Python subprocess with `child_process.spawn` (`stdio: ['pipe', 'pipe', 'inherit']`).
  - Implement `JsonRpcClient`:
  - `sendRequest(method, params): Promise<response>`
  - `sendNotification(method, params): void`
  - Line‑based reading from stdout, parse  NDJSON.
  - Emit events for incoming notifications.
  - Handle `system/ready` notification to confirm warm start.

- [ ] **Python side: RPC server**
  - Read stdin line‑by‑line in an `asyncio` task.
  - Parse JSON-RPC requests and notifications.
  - Register handlers: `agent/run` (core loop), `stream/cancel`.
  - Send streaming notifications back: `stream/textDelta`, `stream/toolCall`, `stream/toolResult`, `stream/end`, `stream/error`.
  - Send `system/ready` after imports complete.

- [ ] **Protocol specification** (shared TypeScript/Python types)
  - Define all request/notification shapes as typed interfaces.
  - Ensure both sides use the same stream ID generation.

## 3. zeno‑ai (Python) – LLM Adapter

- [ ] Wrap LLM logic in an async streaming interface:
  - `def run(prompt: str, messages: list[dict], tools: list[dict], stream: bool = True) -> AsyncIterator[dict]`
  - Output must emit structured events: `{type: "text_delta", content: str}`, `{type: "tool_call", id: str, name: str, args: dict}`, `{type: "stop", reason: str}`.
  - Handle multiple providers using litellm

- [ ] Implement token counting utility (approximate) for pruning on Node side.

## 4. zeno‑agent‑core (Python) – Reasoning Loop & Tools

- [ ] **Agent loop**
- Receive `agent/run` request with `messages`, `tools`, `systemPrompt`.
- Iteratively call `zeno-ai.run()`, collect tool calls, execute them, stream results, continue until stop.
- Support cancellation: listen for `stream/cancel` notification and gracefully abort the loop.

- [ ] **Tool implementations** (all in Python)
- `read(path, offset, limit)` – return content with line numbers, max 200 lines.
- `write(path, content)` – create/overwrite file (no sandboxing yet, just write to disk).
- `edit(path, old_string, new_string)` – require exact unique match, perform single replacement.
- `bash(command)` – execute via `subprocess.run` with timeout, capture stdout/stderr, truncate to 1000 lines.

- [ ] **Tool result formatting**
- Return structured objects: `{ output, truncated, exitCode?, error? }`.
- Mark the stream with `toolResult` notifications.

## 5. zeno‑coding‑agent (Node) – Session & CLI Wrapper

- [ ] **Session manager**
  - Store canonical conversation as `Message[]`.
  - On each user message: append to history, run `prune()`, then dispatch to Python.
  - Pruning logic:
    - Walk messages backwards.
    - Always keep system messages and the latest user/assistant exchange untouched.
    - For earlier assistant/tool pairs, keep only the last 40k tokens (approximate via token counting utility from `zeno-ai`).
    - Drop older tool outputs (or replace with a placeholder).
  - Store session ID, project root, etc.

- [ ] **Permission gate (initial hardcoded)**
  - After receiving `stream/toolCall` for `bash`:
    - Check if command matches dangerous patterns (`rm -rf`, `sudo`, `chmod 777`, `> /dev/sda`, etc.).
    - If dangerous, pause stream, send a `permission/request` event to TUI, wait for user response.
    - If approved, allow the tool execution (or send the `bash` command to Python). Implementation: Node could either block the tool call from being sent to Python, or Node sends a `cancel` + re‑sends a modified `agent/run` with an approval flag. Simpler: Node keeps the `bash` tool on the Node side only and executes it after approval? But Python already has filesystem access. Better: Node intercepts the tool call, asks user, and then tells Python to proceed (maybe via a separate notification `permission/granted`). Design choice – see ideation.
  - For `write`/`edit`: block writes outside project root or to `*.env`, `*.secret`? Low priority, but same gate mechanism.

- [ ] **RPC integration**
  - On user input, call `sendRequest('agent/run', { sessionId, messages: prunedMessages, tools: toolDefs })`.
  - Subscribe to stream notifications and forward events to the TUI renderer.
  - Handle `stream/end` to mark completion.
  - Send `stream/cancel` if user triggers cancellation.

## 6. zeno‑tui (Node) – Terminal UI

- [ ] **Renderer interface**
  - Define abstract `Renderer` class/interface:
    - `updateSection(id, content)`
    - `showPrompt(onSubmit)`
    - `setStatusLine(text)`
    - `requestPermission(message, choices) -> Promise<choice>`
  - **Ink implementation** (initial):
    - Build layout: chat scroll area, prompt input, status bar.
    - Use Ink’s `Box`, `Text`, `useInput` components.
    - Handle keybindings: Ctrl+C to cancel, ArrowUp/Down for history.
    - Display streaming deltas in real time via state updates.
    - Show tool calls as distinguishable bubbles.
  - Ensure the renderer is the only file importing Ink; everything else uses the interface.

- [ ] **UI sections**
  - Chat log – scrollable list of messages with roles.
  - Active tool indicator (e.g., “Running bash: npm test”).
  - Status line – current model, token count, session status.
  - Permission dialog – overlay that captures input for dangerous actions.

  - [ ] **Input handling**
  - Multi‑line editing? (start with single line).
  - History navigation.

## 7. Integration & Startup

- [ ] **Startup script**
  - Node entry point that spawns Python and starts TUI.
  - Python process loads imports and sends `system/ready`.
  - Node displays splash or “Zeno ready”.

- [ ] **Warm startup**
  - The Python process lives as long as the CLI session; no cold start per request.

## 8. Context Pruning – Implementation Details

- [ ] Implement token counting utility (approximate, based on word count or a simple heuristic; later can use an exact tokenizer).
- [ ] `prune(messages: Message[], protectedTokens: number = 40000): Message[]`
  - Ensure the most recent user message and any following assistant messages are kept.
  - Keep system prompts fully.
  - For older tool/assistant blocks, accumulate tokens backwards until limit is hit, discard the rest.
- [ ] Unit tests for pruning with various edge cases (single tool call, many tool calls, huge outputs).

## 9. Error Handling & Resilience

- [ ] **Python crashes/restarts:** Node should detect child process exit and attempt to respawn, notify user.
- [ ] **Tool execution errors:** Python must catch exceptions, return structured error in tool result (do not crash the loop).
- [ ] **Cancellation:** ensure asyncio tasks are properly cancelled, subprocesses killed when a stream is cancelled.

---

## To Ideate Further

A list of open design decisions and future enhancements.

- **Bash sandboxing / permission model**
  - Should the `bash` tool be executed by Python or by Node after approval?
  - How to handle a command that is partially dangerous (e.g., `rm -rf ./some-folder`)? Possibly a pattern‑based allow/deny list.
  - Should the user be able to “always allow” a command for the session?

- **Edit tool behaviour**
  - Exact match required for `old_string`; what if it’s not unique? Return an error with line numbers of matches? Allow multiple replacements?
  - Support for regex? (Probably no, to keep simplicity).

- **Multi‑turn vs single‑turn REPL initial release**
  - Do we start with a full conversation loop with pruning, or a simpler “one shot” mode (user prompt → agent response → exit)?
  - The architecture supports multi‑turn from day one, but we could ship a minimal working version with a single exchange to validate the pipe and TUI.

- **TUI replacement plan**
  - When will we replace Ink? Criteria: once the TUI is feature‑complete enough that rewriting it without React is a net gain in maintainability/simplicity.
  - The in‑house renderer will use raw ANSI commands, a dirty‑row diffing system, and a virtual grid. We need to define the exact feature set needed before starting that build.

- **Config & theming**
  - Initially hardcoded colors/keybindings, but later load from `~/.zenorc` (or similar). The `Renderer` interface should eventually expose a `setTheme(theme)` method.
  - Which theme tokens to define: `accent`, `error`, `info`, `userBubble`, `agentBubble`…

- **Extensions / skills system**
  - How to allow users to add more tools later while keeping the core exactly four? Possibly by having the agent‑core accept a dynamic tool set; the session manager would then register extra tools from extensions.
  - Hot‑reloading of extensions – Node side watches files and re‑registers tools without restarting the Python process? Or just restart the agent core.

- **Testing strategy**
  - Unit tests for each package.
  - Integration test: spawn a real Python process and send RPC requests over stdio.
  - Test TUI components with Ink’s `renderToString`? (Ink provides testing utilities.)

- **Performance & token counting**
  - At what point should exact token counting be implemented (e.g., via `tiktoken`)? Start with rough heuristic; exact counting can be a drop‑in replacement inside the pruning function.
  - Stream batching: should Node coalesce multiple rapid `textDelta` notifications before updating the TUI to avoid React re‑render thrashing? Ink already batches state updates, but explicit throttling could be added to the renderer.

- **Project‑level context loading**
  - AGENTS.md or similar – read a project‑level file and inject it into the system prompt. Should happen in `zeno-coding-agent` before building the message list.
  - Hierarchical loading: global config, then local. Where is the global config stored?

- **Headless mode / alternative UIs**
  - The JSON‑RPC protocol could be exposed as a public API for other frontends. Ensure the protocol is well‑documented and versioned.
  - Should we support a `--headless` flag where the CLI outputs raw streaming events to stdout? That’s a separate renderer implementation.

---

*Note: 1. litellm to be replaced later to use llm providers sdks or faster mechanisms.*

---

*This TODO.md will be updated as design decisions solidify and implementation progresses.*
