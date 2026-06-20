# Zeno — Ultra-Lean AI Coding Harness

**The simplest and fastest AI coding tool possible**, by shedding all traditional over-engineering.

- **Minimal**: no heavy monorepo setups, no virtual DOM overhead, no complex background process management.
- **Fast**: warm Python process lives for the whole CLI session; zero cold starts per request.
- **Stateless on the agent side**: Node sends the full (pruned) message list on every run, so the Python loop is trivial.
- **Exactly 4 tools**: `read`, `write`, `edit`, `bash` — everything you need to code.
- **Cross-platform**: works on Windows, macOS, Linux (primary entry via `node scripts/start.js`).

## Architecture

```arch
┌─ Node (zeno-tui + zeno-coding-agent) ───────┐
│  • CLI + TUI (Ink + plain readline)         │
│  • Session, pruning, permission gate        │
│  └─ RPC client (stdio) ──────────────┐      │
│                                      │      │
│                                      ↓      │
└─────────────────────────────────────────────┘
                                       
                            JSON-RPC 2.0 (NDJSON)
                                       ↕
┌──────────────────────────────────────────────┐
│ Python (zeno-agent-core + zeno-ai)           │
│  • Agent loop + permission handling          │
│  • Tools: read, write, edit, bash            │
│  • RPC server (stdio reader on thread)       │
│  └─ LLM adapter (mock or litellm) ───────────│
└──────────────────────────────────────────────┘
```

### Four Packages

| Package | Language | Role |
| --------- | ---------- | ------ |
| `zeno-ai` | Python | LLM adapter (mock + litellm) + token counter |
| `zeno-agent-core` | Python | Tools, agent loop, JSON-RPC stdio server |
| `zeno-coding-agent` | Node/TS | RPC client, session, pruning, permission gate |
| `zeno-tui` | Node/TS | Renderer interface + Ink + plain CLI |

### Key Design Decisions

- **Offline by default**: built-in `mock` provider (deterministic, no API keys needed) lets you test the entire pipeline without credentials.
- **Zero-dependency core**: Python agent-core uses only stdlib (`asyncio`, `dataclasses`). `litellm` is optional (for real models).
- **Stdout discipline**: Python's stdout is reserved for JSON-RPC NDJSON; logs go to stderr.
- **Cancellation**: cooperative via `asyncio.Event`; user can cancel at any time (Ctrl+C).
- **Permission gate**: safe operations auto-approve; dangerous patterns (e.g., `rm -rf`, `sudo`) and secret files prompt the user.
- **Pruning**: keeps the latest 40k tokens of assistant/tool history, always preserves the active exchange.
- **Renderer fallback**: zero-dependency `PlainRenderer` (readline-based) works even if Ink fails (also serves `--headless` mode).

---

## Quick Start

### Installation

```bash
# Clone the repo
git clone <repo-url>
cd Zeno

# Install dependencies (Node + Python)
npm install
pip install -r requirements.txt

# Build (one-time, or on changes)
npm run build
```

### Run Zeno

```bash
# Start with the mock provider (offline, no API keys)
npm start

# Start with a real model (requires credentials in .env)
npm start -- --model azure/gpt-4o-mini

# Headless mode (no interactive TUI, plain input/output)
npm start -- --headless --model mock

# Custom project root
npm start -- --root ~/my-project --model mock
```

### Inside Zeno

Once running, you'll see a prompt:

```bash
Zeno  ultra-lean AI coding harness
Type your message. /exit to quit, Ctrl+C to cancel.

[mock · 1 msgs · ~53 tok] you:
```

Type any task, e.g.:

- `read README.md` → reads the file
- `write test.py` with content `print("hello")`
- `create a calculator function in calc.py`
- `/exit` → quit

**Ctrl+C while thinking** → cancel the current request.

When a tool call is marked as dangerous, you'll be prompted:

```
permission needed: bash — recursive force delete (rm -rf)
allow? [y/N]
```

Reply `y` to allow or `n` (default) to deny.

---

## Real Models

To use a real LLM provider, set your API credentials in a `.env` file (see `.env.example`), then pass the model:

```bash
# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-... npm start -- --model anthropic/claude-3-5-sonnet-20241022

# Azure OpenAI
AZURE_OPENAI_API_KEY=... npm start -- --model azure/gpt-4o-mini

# Local Ollama
npm start -- --model ollama/llama2
```

Zeno uses **litellm** to talk to these providers (auto-loaded on demand). Install it first if needed:

```bash
pip install litellm
```

---

## Project Structure

```
Zeno/
├── packages/
│   ├── zeno-ai/                  # Python LLM adapter + tokenizer
│   │   ├── zeno_ai/
│   │   │   ├── adapter.py        # LLMAdapter (mock, litellm)
│   │   │   ├── tokens.py         # Token counting heuristic
│   │   │   └── providers/        # mock.py, litellm_provider.py
│   │   └── tests/
│   ├── zeno-agent-core/          # Python agent loop + RPC server
│   │   ├── zeno_agent_core/
│   │   │   ├── main.py           # stdio RPC entry point
│   │   │   ├── rpc.py            # JSON-RPC server
│   │   │   ├── agent.py          # agent loop
│   │   │   └── tools.py          # read, write, edit, bash
│   │   └── tests/
│   ├── zeno-coding-agent/        # Node RPC client + session
│   │   ├── src/
│   │   │   ├── index.ts          # Public API
│   │   │   ├── rpcClient.ts      # Spawn + talk to Python
│   │   │   ├── session.ts        # History + pruning
│   │   │   ├── permission.ts     # Permission gate
│   │   │   ├── protocol.ts       # Shared types
│   │   │   ├── prune.ts          # Context pruning logic
│   │   │   └── tokens.ts         # Token counter mirror
│   │   └── dist/                 # Compiled JS
│   └── zeno-tui/                 # Node terminal UI
│       ├── src/
│       │   ├── cli.ts            # CLI entry + REPL loop
│       │   ├── renderer.ts       # Renderer interface
│       │   ├── inkRenderer.tsx   # Ink (React) renderer
│       │   ├── plainRenderer.ts  # Zero-dep readline renderer
│       │   └── ...
│       └── dist/                 # Compiled JS
├── scripts/
│   ├── start.js                  # Cross-platform launcher
│   └── start.sh                  # Bash wrapper
├── examples/                     # Example projects & tasks
│   ├── calculator/               # Python calculator app
│   ├── todo-cli/                 # Todo list CLI
│   └── ...
├── package.json                  # Root npm workspace
├── tsconfig.json                 # TypeScript config (shared)
├── requirements.txt              # Python dependencies
├── TODO.md                        # Implementation roadmap
└── README.md                      # This file
```

---

## Examples

See the `examples/` folder for projects Zeno can help you build. Each includes a description and optional "scaffolding hints" (tasks to give to Zeno).

### Calculator (Python)

A simple arithmetic CLI app with history and undo.

**Try it:**

```bash
npm start -- --model mock

# At the prompt:
read examples/calculator/README.md
read examples/calculator/requirements.txt
# ... then ask: "Implement the calculator app from the spec in examples/calculator/README.md"
```

Or explore the code:

```bash
less examples/calculator/README.md
```

### Todo CLI (Node)

A command-line todo manager with persisted state.

**Try it:**

```bash
npm start -- --model mock

# At the prompt:
read examples/todo-cli/README.md
# ... then ask: "Implement the todo CLI from examples/todo-cli/README.md"
```

---

## Testing

```bash
# Run all tests (Python + Node)
npm run test:py
npm run test:node
# or combined: npm run build && npm run test:py && npm run test:node

# Watch mode (rebuild + retest on file changes)
npm run build -- --watch
```

---

## Environment Variables

Create a `.env` file in the repo root (or per project via `--root`):

```bash
# Model selection
ZENO_MODEL=mock                    # or: anthropic/claude-3-5-sonnet, azure/gpt-4o-mini, etc.

# API Keys (for litellm providers)
ANTHROPIC_API_KEY=sk-ant-...
AZURE_OPENAI_API_KEY=...
AZURE_OPENAI_ENDPOINT=...
...

# Path to Python executable (if not in PATH)
ZENO_PYTHON=python3.13
```

---

## Limitations & Future Work

- **v0 doesn't have:**
  - Multi-line editing in the plain renderer (single-line prompts for now).
  - Command history / arrow-key navigation (readline doesn't expose it cleanly).
  - Exact token counting (rough heuristic is fine for pruning).
  - Bash sandboxing (all commands run freely after user approval).

- **Planned:**
  - In-house renderer to replace Ink (zero dependencies, faster startup, custom keybindings).
  - Workspace/project config (`zeno.json` or `AGENTS.md` injection).
  - Extension/skills system (dynamic tools beyond the core four).
  - Real token counting via `tiktoken`.
  - Streaming tool output directly to TUI (no batching).

---

## Development

```bash
# Full build from scratch
npm run build

# Run Zeno (post-build)
npm start

# Run tests
npm run test:py && npm run test:node

# Check lint (TypeScript strict mode)
npm run build 2>&1 | grep error

# Clean build artifacts
rm -rf packages/*/dist packages/*/__pycache__ .pytest_cache
```

---

## Contributing

Zeno is intentionally minimal. Before adding features, ask:

- **Does it add essential value, or is it convenience?** Zeno prioritizes leanness.
- **Can the TUI stay swappable?** All UI-facing logic must go through the `Renderer` interface.
- **Is it cross-platform?** Test on Windows, macOS, Linux.
- **Does it maintain warm startup?** The Python process should stay alive for the session.

---

## License

MIT

---

## Quick Troubleshooting

| Problem | Solution |
| --------- | ---------- |
| `python: command not found` | Set `ZENO_PYTHON=python3` in `.env` or `npm start -- --python python3` |
| `Error: Cannot find module 'ink'` | Run `npm install` at repo root, then `npm run build` |
| `permission denied: bash — ...` | Reply `y` at the prompt to allow, or use `--model mock` to skip real bash |
| Ink crashes on Windows | Use `npm start -- --headless` for the plain readline renderer |
| Model not found (litellm) | Install it: `pip install litellm` |

---

**Ready to build?** Start Zeno now:

```bash
npm start
```

Enjoy!
