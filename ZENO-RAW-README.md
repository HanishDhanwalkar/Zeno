# Zeno — The Essence

## **Core Identity**

- A high-performance, minimalist AI coding harness built on Unix philosophy
- Dual-runtime hybrid: Node.js owns the UI/session layer, Python owns the intelligence layer
- Long-running JSON-RPC 2.0 stdio pipe eliminates process startup latency between runtimes
- Modular design split into exactly 4 packages with strict boundaries

## **The Four Packages**

- `zeno-tui` — flicker-free terminal UI, third-party libs now, replaceable with in-house renderer later
- `zeno-coding-agent` — CLI wrapper, session tracker, context management, permission gates
- `zeno-agent-core` — agent reasoning loop, tool execution (stateless, receives full context each run)
- `zeno-ai` — thin, stateless LLM adapter, streaming, provider-agnostic

## **Tools (Only core 4 forever, extensible depending on the requirement)**

- `read` — file content with line numbers, paginated
- `write` — create/overwrite files
- `edit` — single exact-match search-and-replace
- `bash` — shell commands with permission gating for destructive patterns

## **Context Management (current) | More research on this in-progress**

- Compacts after every user message, not just on overflow
- Keeps system messages + latest exchange + tail of 40k tokens from older assistant/tool pairs
- Prevents prompt cache busting, keeps latency low

## **Simplicity Principles**

**Core-Idea**

- No unnecessary boilerplate, no over-engineering
- Each package testable and replaceable independently
- Python side holds no long-lived state between runs
- Exactly 5 JSON-RPC methods total — nothing more
- Agent composes solutions from 4 primitives only

**Safety**

- Destructive bash commands blocked until user confirms through TUI
- Writes gated from protected files and outside project root
- All tools return structured errors, never crash the pipe

**Extensibility (Future)**

- Custom compaction strategies, permission handlers, themes, extensions
- Skills loaded on demand, hot-reload without restart
- Headless JSON streaming mode for alternative UIs
- All built on today's minimal foundation with clear seams

**Technical Constraints**

- Node.js for async stream handling and terminal manipulation
- Python for code parsing, ML libs, complex tool execution
- NDJSON transport over stdio, no HTTP overhead
- Asyncio-based event loop on Python side
- React/Ink TUI initially, abstracted behind `Renderer` interface for later zero-dep replacement
