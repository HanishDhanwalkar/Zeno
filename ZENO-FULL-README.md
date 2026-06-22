# Zeno — AI Coding Assistant with Token Rewards

## Core Identity

- A high-performance, minimalist AI coding harness built on Unix philosophy
- Dual-runtime hybrid: Node.js owns the UI/session layer, Python owns the intelligence layer
- Long-running JSON-RPC 2.0 stdio pipe eliminates process startup latency between runtimes
- Modular design split into exactly 4 packages with strict boundaries
- **Hybrid model**: Open-source client + hosted service with token rewards (optional)

---

## The Four Packages

| Package | Language | Role |
| --------- | ---------- | ------ |
| `zeno-tui` | Node/TS | Flicker-free terminal UI, Ink + plain readline fallback |
| `zeno-coding-agent` | Node/TS | CLI wrapper, session tracker, context management, permission gates, **wallet integration** |
| `zeno-agent-core` | Python | Agent reasoning loop, tool execution (stateless, receives full context each run) |
| `zeno-ai` | Python | Thin, stateless LLM adapter, streaming, provider-agnostic |

---

## Tools (Only core 4 forever, extensible depending on the requirement)

- `read` — file content with line numbers, paginated
- `write` — create/overwrite files
- `edit` — single exact-match search-and-replace
- `bash` — shell commands with permission gating for destructive patterns

---

## Context Management (current) | More research on this in-progress

- Compacts after every user message, not just on overflow
- Keeps system messages + latest exchange + tail of 40k tokens from older assistant/tool pairs
- Prevents prompt cache busting, keeps latency low

---

## Token Rewards System (Optional Hosted Service)

### How It Works

```
User pays $100 to Zeno Gateway (prepaid credits)
    ↓
Gateway buys LLM API capacity at $80 (bulk discount)
    ↓
Gateway keeps $20 margin
    ↓
Gateway mints $4 in ZENO tokens (20% rebate on user's cost)
    ↓
Gateway keeps $16 for operations + profit
```

### Token Economics (Brave-inspired Model)

```
Total Supply: 1,000,000,000 ZENO (fixed, no inflation)

Allocation:
├─ Team + Treasury: 600M (60%) — funds operations, development
├─ User Rewards: 300M (30%) — distributed over 3 years based on usage
└─ Community + Ecosystem: 100M (10%) — grants, partnerships, liquidity

Vesting:
├─ Team: 4-year vesting (1-year cliff)
├─ User Rewards: Linear distribution (daily)
└─ Ecosystem: 2-year vesting
```

### Token Utility

- **Governance**: Vote on reward rates, feature priority, new model integrations
- **Premium discounts**: Holders get discounts on premium tiers
- **Staking**: Earn API credits by staking ZENO
- **Community treasury**: Revenue share for token holders (DAO)

### Two Modes of Operation

| Mode | Description | Rewards |
| ------ | ------------- | --------- |
| **Local** | BYO API keys, free, offline | ❌ No rewards |
| **Hosted** | Pay Zeno, no API keys needed | ✅ 20% back in ZENO tokens |

---

## Security

### Wallet Isolation

```wallet
┌─────────────────────────────────────────┐
│  Main Process (Node)                    │
│  • TUI                                  │
│  • Session management                   │
│  • Bash tool (unsandboxed)              │
│  • NO wallet keys here                  │
└─────────────────────────────────────────┘
                    ↕ Encrypted IPC
┌─────────────────────────────────────────┐
│  Wallet Process (Isolated)              │
│  • Encrypted wallet storage             │
│  • Signing only (no key exposure)       │
│  • Requires explicit approval per tx    │
└─────────────────────────────────────────┘
```

### Transaction Approval Flow

1. User completes API call
2. Gateway calculates reward
3. Gateway proposes transaction
4. Client shows: "Claimed X ZENO"
5. User approves → Wallet signs → Transaction
6. Reward deposited

### Anti-Abuse Measures

| Threat | Mitigation |
| -------- | ------------ |
| Sybil attacks | Device fingerprinting + IP-based rate limits + email verification |
| Token count cheating | Server-side tiktoken with signed receipts |
| API call spoofing | Cryptographic request signing |
| Multiple accounts | KYC for high-earning users |
| Flash loan oracle attacks | Chainlink price feeds with multiple oracles |
| Wallet theft | Isolated wallet process + hardware wallet support |

---

## Simplicity Principles

### Core Idea

- No unnecessary boilerplate, no over-engineering
- Each package testable and replaceable independently
- Python side holds no long-lived state between runs
- Exactly 5 JSON-RPC methods total — nothing more
- Agent composes solutions from 4 primitives only
- **Rewards system is separate from core client**

### Safety

- Destructive bash commands blocked until user confirms through TUI
- Writes gated from protected files and outside project root
- All tools return structured errors, never crash the pipe
- **Wallet keys never exposed to ai agents or bash tool or main process**

### Extensibility (Future)

- Custom compaction strategies, permission handlers, themes, extensions
- Skills loaded on demand, hot-reload without restart
- Headless JSON streaming mode for alternative UIs
- All built on today's minimal foundation with clear seams
- **Rewards system can be extended with new token utilities**

---

## Technical Constraints

- Node.js for async stream handling and terminal manipulation
- Python for code parsing, ML libs, complex tool execution
- NDJSON transport over stdio, no HTTP overhead
- Asyncio-based event loop on Python side
- React/Ink TUI initially, abstracted behind `Renderer` interface for later zero-dep replacement
- **Wallet process isolated from main process for security**
- **Hosted gateway uses exact token counting (tiktoken)**

---

## Hosted Service Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Zeno Client (Open Source — MIT)                         │
│  • CLI + VSCode Extension                                │
│  • 4 tools (read, write, edit, bash)                     │
│  • Communicates with hosted gateway via REST/WebSocket   │
│  • Wallet management (isolated process)                  │
│  • NO API keys stored locally                            │
└──────────────────────────────────────────────────────────┘
                           ↕ HTTPS
┌──────────────────────────────────────────────────────────┐
│  Zeno Gateway (Hosted Service)                           │
│  • Authentication (user accounts + wallets)              │
│  • LLM API relay (bulk pricing from providers)           │
│  • Usage tracking (exact token counting with tiktoken)   │
│  • Billing (prepaid credits or postpaid)                 │
│  • Reward calculation (20% rebate in ZENO tokens)        │
│  • Token issuance (ERC-20 minting)                       │
│  • Anti-abuse + rate limiting                            │
└──────────────────────────────────────────────────────────┘
                           ↕ Blockchain
┌──────────────────────────────────────────────────────────┐
│  ZENO Token Contract + Liquidity                         │
│  • ERC-20 token with fixed supply                        │
│  • Uniswap pool for liquidity                            │
│  • Governance + staking (future)                         │
└──────────────────────────────────────────────────────────┘
```

---

## Project Structure

```file-structure
Zeno/
├── packages/
│   ├── zeno-client/               # Open-source CLI + VSCode extension
│   │   ├── src/
│   │   │   ├── cli.ts             # CLI entry point
│   │   │   ├── session.ts         # Session management
│   │   │   ├── tools/             # read, write, edit, bash
│   │   │   ├── wallet/            # Isolated wallet process
│   │   │   └── protocol.ts        # Shared types
│   │   └── dist/                  # Compiled JS
│   ├── zeno-gateway/              # Hosted relay service
│   │   ├── src/
│   │   │   ├── index.ts           # Server entry
│   │   │   ├── relay.ts           # LLM API relay
│   │   │   ├── billing.ts         # Payment processing
│   │   │   ├── rewards.ts         # Token calculation
│   │   │   ├── counting.ts        # tiktoken integration
│   │   │   └── auth.ts            # Authentication
│   │   └── tests/
│   ├── zeno-contracts/            # Smart contracts
│   │   ├── contracts/
│   │   │   ├── ZenoToken.sol      # ERC-20 token
│   │   │   └── Rewards.sol        # Reward distribution
│   │   └── tests/
│   ├── zeno-agent-core/           # Python agent loop
│   ├── zeno-ai/                   # Python LLM adapter
│   └── zeno-tui/                  # Terminal UI
├── scripts/
│   ├── start.js                   # Cross-platform launcher
│   └── start.sh                   # Bash wrapper
├── package.json                   # Root npm workspace
├── tsconfig.json                  # TypeScript config
├── requirements.txt               # Python dependencies
└── README.md                      # This file
```

---

## Development Phases

### Phase 1: Foundation

- Open-source client (CLI + VSCode extension)
- 4 core tools (read, write, edit, bash)
- Local mode with BYO API keys
- Mock provider for testing

### Phase 2: Hosted Service

- Hosted gateway with authentication
- LLM API relay with bulk pricing
- Exact token counting (tiktoken)
- Billing (prepaid credits)
- Reward calculation engine

### Phase 3: Token Integration

- ZENO ERC-20 token deployment
- Uniswap liquidity pool
- Reward minting and distribution
- Wallet isolation for security

### Phase 4: Community

- Governance DAO
- Premium features
- Exchange listings
- Enterprise tier
- Hardware wallet support

---

## Contributing

Zeno follows a hybrid model:

### Core Client (Open Source)

- Keep it lean: exactly 4 tools
- Zero blockchain dependencies in client
- All UI logic through `Renderer` interface
- Cross-platform testing (Windows, macOS, Linux)
- **No API keys required for local mode**

### Gateway + Contracts (Open Source with Hosted Service)

- Open-source for auditability
- Hosted service is the reference implementation
- Anyone can self-host (BYO providers)
- Contributions welcome

### Before Adding Features, Ask

1. **Essential or convenience?** Zeno prioritizes leanness.
2. **Does it break the 4-tool promise?** If yes, reconsider.
3. **Is the wallet isolated?** Security is non-negotiable.
4. **Can it be self-hosted?** Open-source alternatives should be possible.

---

*Note:*\
*- `Renderer` interface is currently open-source INK renderer*\
*- The discounts or the backback of 20% is figurative and place holder for now; the bulk discounts from llm providers is in-progress*
