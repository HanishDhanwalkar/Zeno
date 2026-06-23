# CodeAssist - AI Coding Assistant with Token Rewards

An AI-powered coding assistant that rewards developers with native tokens for every LLM interaction. Built as a CLI tool and VS Code extension.

---

## Overview

CodeAssist is an AI coding assistant that integrates with your development workflow. Behind the scenes, it leverages multiple LLM providers (OpenAI, Anthropic, etc.) to power code completion, explanation, generation, and debugging. Every interaction earns users token rewards based on actual LLM usage.

---

## How It Works

### User Flow

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│  1. Developer installs CodeAssist CLI or VS Code extension    │
│                                                               │
│  2. Connects wallet                                           │
│                                                               │
│  3. Starts coding with AI assistance:                         │
│     └─ everything that cursor or claude code does             │
│        but in the simplest and fastest version of both        │
│                                                               │
│  4. Each AI interaction:                                      │
│     ├─ Calls LLM API behind the scenes                        │
│     ├─ Cost tracked per request                               │
│     └─ 20% of API cost minted as tokens to user's wallet      │
│                                                               │
│  5. Tokens accumulate and can be:                             │
│     ├─ Used for premium features                              │
│     ├─ Used for governance voting                             │
│     ├─ Staked for additional API credits                      │
│     └─ Traded on exchanges                                    │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

*Note: the 20% above is not finalised yet. Use similar property or percent method brave use*

### Business Model

```
┌───────────────────────────────────────────────────────────────┐
│                                                               │
│  REVENUE STREAMS:                                             │
│  ├─ Premium Tier: $20/month (unlimited, faster models)        │
│  ├─ Enterprise: $50-100/user/month (team plans, SLAs)         │
│  └─ Future: Sponsored integrations                            │
│                                                               │
│  COST STRUCTURE:                                              │
│  ├─ LLM API costs (bought in bulk at discount)                │
│  └─ Infrastructure & operations                               │
│                                                               │
│  TOKEN REWARDS:                                               │
│  ├─ Funded by premium revenue + API margin                    │
│  ├─ 20% rebate of API cost per interaction                    │
│  └─ Minted real-time to user wallets                          │
│                                                               │
└───────────────────────────────────────────────────────────────┘
```

*Note: 20% is placeholder num. The discount from llm provider is not finalised yet*

---

## Token Economics

### Token Supply

| Allocation | Amount | Purpose |
| ------------ | -------- | --------- |
| Team/Treasury | 600M (60%) | Development funding via appreciation |
| User Rewards | 300M (30%) | Distributed to users over 3-5 years |
| Ecosystem | 100M (10%) | Partnerships, grants, integrations |
| **Total** | **1B** | Fixed supply, no inflation |

### Reward Rate

- Users earn tokens equal to **20% of the USD cost** of each LLM API call or precisely on token usage
- Example: An interaction costing $0.05 earns $0.01 worth of tokens
- Rewards tracked per user and minted on-chain

### Token Utility

| Utility | Description |
| --------- | ------------- |
| **tradable asest** | User can swapp this tokens against any crypto like BTC or ETH |
| **Governance** | Vote on feature priorities, integrations |
| **Premium Discounts** | Token holders get 10% (not finalised) off pro subscription and premium features for payment done by token |
| **Staking** | Stake tokens to earn additional API credits |
| **Appreciation** | Token value increases as platform grows |

### Funding Mechanism

Following the Brave BAT model:

- Team holds 60% of total token supply
- Tokens appreciate as user base grows
- Treasury tokens can be sold to fund development
- No VC dilution—founders retain control

---

## Technology Stack

### Components

| Layer | Technology |
| ------- | ------------ |
| **Frontend** | CLI tool, VS Code extension |
| **LLM Integration** | OpenAI, Anthropic, Groq (multiple providers) |
| **Token Contract** | ERC-20 on L2 (Arbitrum/Optimism) |
| **Reward Tracking** | Off-chain calculation with on-chain minting |
| **Price Oracle** | Chainlink for token price feeds |
| **Wallet** | Account abstraction (email → wallet) |
| **Anti-Abuse** | Device fingerprinting, IP limits, signed payloads |

### Smart Contract

```solidity
contract CodeAssistToken is ERC20 {
    // Minting restricted to reward manager
    function mintReward(address user, uint256 amount) external onlyRewardManager {
        _mint(user, amount);
    }
    
    // Fixed supply, no inflation
    uint256 public constant MAX_SUPPLY = 1_000_000_000 * 10**18;
}
```

---

## Development Roadmap

### Phase 1: Foundation (Month 1-3)

| Task | Status | Details |
| ------ | -------- | --------- |
| CLI tool | [ ] | Core coding assistant functionality |
| VS Code extension | [ ] | Main distribution channel |
| LLM provider integration | [ ] | OpenAI, Anthropic API connections |
| Bulk discount agreement | [ ] | Negotiate volume pricing with providers |

### Phase 2: Token Integration (Month 3-5)

| Task | Status | Details |
| ------ | -------- | --------- |
| Wallet connection | [ ] | Account abstraction for easy onboarding |
| Token contract deployment | [ ] | ERC-20 on L2 (Arbitrum) |
| Reward tracking system | [ ] | Track API usage per user |
| Token minting logic | [ ] | Real-time or batched minting |
| Price oracle integration | [ ] | Chainlink for USD → token conversion |
| Anti-abuse system | [ ] | Rate limits, verification, monitoring |

### Phase 3: Launch (Month 5-7)

| Task | Status | Details |
| ------ | -------- | --------- |
| Beta launch | [ ] | 5,000 users for validation |
| Reward distribution | [ ] | Start minting tokens to users |
| Uniswap liquidity | [ ] | Bootstrap with $500K stablecoins + tokens |
| Token dashboard | [ ] | Users see rewards, transactions, holdings |
| Marketing campaign | [ ] | Target AI coding assistant users |

### Phase 4: Growth (Month 7-12)

| Task | Status | Details |
| ------ | -------- | --------- |
| Premium tier launch | [ ] | $20/month for unlimited features |
| Enterprise plans | [ ] | Team features, admin controls, SLAs |
| Exchange listing | [ ] | Kraken/Coinbase (6-12 months post-launch) |
| Community DAO | [ ] | Token holder governance |
| Ecosystem partnerships | [ ] | Integrations with other developer tools |

### Phase 5: Scale (Year 2+)

| Task | Status | Details |
| ------ | -------- | --------- |
| 500K+ users | [ ] | Scale token value through network effects |
| Treasury sales | [ ] | Sell small % of treasury for funding |
| Additional LLM providers | [ ] | Expand beyond OpenAI/Anthropic |
| Sponsored integrations | [ ] | Brand partnerships for revenue |
| Mobile/web app | [ ] | Expand beyond VS Code/CLI |

---

## Anti-Abuse Measures

| Threat | Mitigation |
| -------- | ------------ |
| Sybil attacks | Device fingerprinting + IP + email verification |
| API call spoofing | Signed requests, usage proof, quality checks |
| Oracle manipulation | Chainlink + fallback oracle with median pricing |
| Rate limit bypass | Per-wallet + per-IP + per-device limits |
| Farming | Monitoring reward/cost ratio (keep under 25-30%) |

---

## Legal & Regulatory

### Framework

Following the Brave BAT precedent:

- Token positioned as **utility token** (loyalty/governance), not security
- Users earn tokens for product usage, not wages
- No equity claim or profit-sharing guarantees
- Token unlocks features (governance, discounts, staking)

### Compliance

| Requirement | Approach |
| ------------- | ---------- |
| KYC/AML | Implement for high-earning users |
| Tax reporting | Users responsible for tax on rewards |
| Regional restrictions | Start in crypto-friendly jurisdictions |
| Legal review | $15-20K budget for crypto lawyer |

---

## Key Metrics

| Metric | Target |
| -------- | -------- |
| Initial users | 5,000 (beta) |
| Scale users | 100,000+ (Year 1) |
| Premium adoption | 20-30% of free users |
| Token price appreciation | 10-20x by Year 2 |
| Monthly revenue | $1M+ (Year 2) |
| Token supply | 1B fixed |

---

## Risks & Mitigations

| Risk | Severity | Mitigation |
| ------ | ---------- | ------------ |
| Bulk discount unavailable | High | Negotiate early; adjust reward rate if needed |
| User adoption slow | High | Strong marketing; focus on UX differentiation |
| Token price collapse | Medium | Build real utility (governance, discounts) |
| Regulatory crackdown | Medium | Brave precedent; legal review early |
| Competition (Cursor/Copilot) | Medium | Token rewards as key differentiator |

---

## Getting Started

### For Users

```bash
# Install CLI
npm install -g codeassist

# Install VS Code extension
# Search "CodeAssist" in VS Code marketplace

# Connect wallet
codeassist login

# Start coding
codeassist ask "write a function to fetch data from API"

# Check rewards
codeassist balance
```

### For Developers

```bash
# Clone repository
git clone https://github.com/codeassist/codeassist.git

# Install dependencies
npm install

# Run development
npm run dev

# Deploy token contract
npm run deploy:token

# Run tests
npm test
```

---

## License

MIT

---

## Contact

- Website: [codeassist.ai](https://codeassist.ai)
- Twitter: [@codeassist](https://twitter.com/codeassist)
- Discord: [discord.gg/codeassist](https://discord.gg/codeassist)

---

## Acknowledgments

- Brave Browser for the BAT token model
- Cursor and Copilot for AI coding assistant inspiration
- OpenAI and Anthropic for LLM APIs
