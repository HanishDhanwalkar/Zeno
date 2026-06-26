# Blockchain Wallet Integration: Run & Test Guide

## Overview

The `@zeno/wallet` package provides HD seed-based Ethereum wallet functionality. This guide explains how to run, test, and integrate the wallet with the Zeno coding agent.

---

## Quick Start (5 minutes)

### 1. Install Dependencies

```bash
npm install
```

This installs all workspace packages:
- `@zeno/wallet` - Independent blockchain wallet
- `zeno-coding-agent` - Session management (imports wallet)
- `zeno-tui` - Terminal UI
- `zeno-agent-core` - Python agent (pip install requirements.txt)

### 2. Run Tests

```bash
# Run all Node tests (wallet + agent tests)
npm run test:node

# Run wallet tests only
npm run test --workspace=@zeno/wallet

# Run coding-agent tests only
npm run test --workspace=zeno-coding-agent

# Run Python tests
npm run test:py
```

**Expected result:** All tests pass (12 wallet + 30 coding-agent + 17 Python tests)

### 3. Build All Packages

```bash
npm run build

# Or build specific package
npm run build --workspace=@zeno/wallet
```

---

## Architecture

### Package Structure

```
packages/
├── zeno-wallet/              # 🔗 Independent blockchain package
│   ├── src/
│   │   ├── manager.ts        # WalletManager class
│   │   ├── manager.test.ts   # Unit tests
│   │   └── index.ts          # Public exports
│   ├── package.json
│   └── tsconfig.json
├── zeno-coding-agent/        # Session management
│   ├── src/
│   │   ├── session.ts        # Imports from @zeno/wallet
│   │   └── ...
│   ├── package.json          # Depends on @zeno/wallet
│   └── ...
└── zeno-tui/               # Terminal UI
    └── ...
```

### Dependency Flow

```
zeno-tui → zeno-coding-agent → @zeno/wallet
                            ↘ (types only)
```

**Key principle:** Wallet is completely independent. Session manager imports only what it needs.

---

## Using the Wallet

### Basic Usage (TypeScript)

```typescript
import { WalletManager, type WalletConfig } from "@zeno/wallet";

// Create wallet manager
const config: WalletConfig = {
  rpcUrl: "https://sepolia.infura.io/v3/YOUR-PROJECT-ID",
  chainId: 11155111, // Sepolia testnet
  walletPath: "~/.zeno/wallet.json" // Optional: persist wallet
};

const wallet = new WalletManager(config);

// Create new wallet (generates random mnemonic)
const state = await wallet.createWallet();
console.log("Address:", state.address);
console.log("Mnemonic:", state.mnemonic); // Store this securely!

// Or restore existing wallet
const existing = await wallet.loadWallet();
if (existing) {
  console.log("Restored wallet at:", existing.address);
}

// Get wallet address
const address = wallet.getAddress();
console.log("Current address:", address);

// Get balance
const balanceWei = await wallet.getBalance();
console.log("Balance (wei):", balanceWei);

// Estimate gas for transaction
const gasEstimate = await wallet.estimateGas({
  to: "0x1234567890123456789012345678901234567890",
  value: "1000000000000000000" // 1 ETH in wei
});
console.log("Estimated gas:", gasEstimate.gasLimit);
console.log("Estimated cost:", gasEstimate.estimatedCost);

// Sign and broadcast transaction
const result = await wallet.signAndBroadcast({
  to: "0x1234567890123456789012345678901234567890",
  value: "1000000000000000000"
});

if (result.success) {
  console.log("Transaction sent:", result.txHash);
  console.log("Confirmations:", result.confirmationBlocks);
} else {
  console.error("Transaction failed:", result.error);
}

// Clean up
wallet.destroy();
```

### Integration with SessionManager

```typescript
import { SessionManager, type SessionOptions } from "zeno-coding-agent";
import { createAgentCoreClient } from "zeno-coding-agent";
import { getDefaultWalletPath } from "@zeno/wallet";

const sessionOpts: SessionOptions = {
  client: createAgentCoreClient(),
  projectRoot: "/path/to/project",
  walletConfig: {
    rpcUrl: "https://sepolia.infura.io/v3/YOUR-PROJECT-ID",
    chainId: 11155111,
    walletPath: getDefaultWalletPath() // ~/.zeno/wallet.json
  }
};

const session = new SessionManager(sessionOpts);

// Initialize wallet (create or restore)
await session.initializeWallet();

// Now both session and wallet are ready
// Wallet accessible via session.wallet
if (session.wallet) {
  const address = session.wallet.getAddress();
  console.log("Session wallet address:", address);
}

// Clean up
session.destroy(); // Also destroys wallet
```

---

## Testing Strategies

### Unit Tests (No Network Required)

The wallet test suite validates:
- **Structure**: Wallet initialization, config validation
- **BIP-39/BIP-44**: Mnemonic and derivation path formats
- **Security**: File permissions (0o600 for restricted access)
- **Types**: All public methods and interfaces
- **Error handling**: Proper exceptions before wallet init

Run with:
```bash
npm run test --workspace=@zeno/wallet
```

### Integration Tests (Requires Testnet)

To test against actual testnet:

1. **Set up Sepolia RPC endpoint**
   ```bash
   export INFURA_PROJECT_ID="your-project-id"
   ```

2. **Create test wallet script** (`test-wallet.ts`):
   ```typescript
   import { WalletManager } from "@zeno/wallet";

   const wallet = new WalletManager({
     rpcUrl: `https://sepolia.infura.io/v3/${process.env.INFURA_PROJECT_ID}`,
     chainId: 11155111
   });

   // Generate new wallet
   const state = await wallet.createWallet();
   console.log("Test wallet created:", state.address);

   // Get balance (should be 0 initially)
   const balance = await wallet.getBalance();
   console.log("Balance:", balance, "wei");

   // Fund wallet from Sepolia faucet:
   // https://www.sepoliafaucet.com/

   // Test gas estimation
   const gas = await wallet.estimateGas({
     to: "0x0000000000000000000000000000000000000000",
     value: "1000000000000000" // 0.001 ETH
   });
   console.log("Gas estimate:", gas);

   wallet.destroy();
   ```

3. **Run integration test**
   ```bash
   npx ts-node test-wallet.ts
   ```

### Testing Checklist

- [ ] Unit tests pass: `npm run test --workspace=@zeno/wallet`
- [ ] Coding-agent tests pass: `npm run test --workspace=zeno-coding-agent`
- [ ] Wallet initializes without network: ✓
- [ ] Wallet can load from disk after creation: ✓
- [ ] Public API methods exist: ✓
- [ ] Error messages are descriptive: ✓

---

## Testnet Setup (Sepolia)

### Step 1: Get Infura Project ID

1. Sign up at https://infura.io/
2. Create new project
3. Copy Project ID

### Step 2: Fund Test Wallet

1. Get Sepolia ETH from faucet: https://www.sepoliafaucet.com/
2. Enter your wallet address
3. Wait for confirmation (~1 minute)

### Step 3: Configure Environment

```bash
export INFURA_PROJECT_ID="your-project-id"
export WALLET_MNEMONIC="your 12-word mnemonic" # Optional for testing
export WALLET_PATH="~/.zeno/wallet.json"
```

### Step 4: Test Transaction

```typescript
import { WalletManager } from "@zeno/wallet";

const wallet = new WalletManager({
  rpcUrl: `https://sepolia.infura.io/v3/${process.env.INFURA_PROJECT_ID}`,
  chainId: 11155111,
  walletPath: process.env.WALLET_PATH
});

// Load or create wallet
let state = await wallet.loadWallet();
if (!state) {
  state = await wallet.createWallet();
  console.log("New wallet created:", state.address);
  console.log("Fund this address from Sepolia faucet");
}

// Send test transaction
const result = await wallet.signAndBroadcast({
  to: "0x0000000000000000000000000000000000000000", // Burn address
  value: "1000000000000000" // 0.001 ETH
});

if (result.success) {
  console.log("✓ Transaction confirmed!");
  console.log("  Hash:", result.txHash);
  console.log("  Blocks:", result.confirmationBlocks);
} else {
  console.log("✗ Transaction failed:", result.error);
}

wallet.destroy();
```

---

## API Reference

### WalletManager

#### Constructor
```typescript
new WalletManager(config: WalletConfig)
```

#### Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `createWallet(mnemonic?, path?)` | `Promise<WalletState>` | Create new or import wallet |
| `loadWallet()` | `Promise<WalletState \| null>` | Load from disk |
| `getAddress()` | `string` | Get current wallet address |
| `getBalance()` | `Promise<string>` | Get balance in wei |
| `getNonce()` | `Promise<number>` | Get transaction count |
| `estimateGas(params)` | `Promise<GasEstimate>` | Estimate gas for transaction |
| `sign(params)` | `Promise<string>` | Sign transaction (returns hex) |
| `broadcast(signedTx)` | `Promise<BroadcastResult>` | Broadcast signed transaction |
| `signAndBroadcast(params)` | `Promise<BroadcastResult>` | Sign and broadcast in one call |
| `destroy()` | `void` | Clear keys from memory |

### Types

```typescript
interface WalletConfig {
  rpcUrl: string;           // JSON-RPC endpoint
  chainId: number;          // Ethereum chain ID (1 = mainnet, 11155111 = Sepolia)
  walletPath?: string;      // Optional path to persist wallet state (~/.zeno/wallet.json)
}

interface WalletState {
  mnemonic: string;         // BIP-39 12-word seed phrase
  derivationPath: string;   // BIP-44 path (m/44'/60'/0'/0/0)
  address: string;          // Wallet address (0x...)
  nonce: number;            // Transaction count from network
}

interface TransactionParams {
  to: string;               // Recipient address
  value?: string;           // Amount in wei
  data?: string;            // Encoded function call (0x for transfers)
  gasLimit?: string;        // Override gas limit
  gasPrice?: string;        // Legacy gas price (wei)
  maxFeePerGas?: string;    // EIP-1559 max fee (wei)
  maxPriorityFeePerGas?: string; // EIP-1559 priority fee (wei)
}

interface BroadcastResult {
  success: boolean;
  txHash?: string;          // Transaction hash if sent
  receipt?: TransactionReceipt; // Full receipt on success
  error?: string;           // Error message if failed
  confirmationBlocks?: number;
}
```

---

## Common Issues

### Issue: "Wallet not initialized"
**Solution:** Call `createWallet()` or `loadWallet()` before using wallet.

### Issue: "Cannot read property 'fromMnemonic'"
**Solution:** Ensure ethers.js v6.11.0+ is installed: `npm install ethers@^6.11.0`

### Issue: "Transaction confirmation timeout"
**Solution:** Network congestion. Try again or increase timeout (120s default).

### Issue: Wallet file permission denied
**Solution:** Check ~/.zeno/ directory permissions: `chmod 700 ~/.zeno/`

### Issue: "RPC error: insufficient funds"
**Solution:** Fund testnet wallet from faucet: https://www.sepoliafaucet.com/

---

## Security Notes

⚠️ **WARNING**: This wallet implementation is for development/testing only.

### For Production:
- [ ] Use hardware wallet support (Ledger/Trezor) - `blockchain/hardware-wallet` branch
- [ ] Implement rate limiting - `blockchain/sybil-defense` branch
- [ ] Add transaction approval UI - `blockchain/tx-approval-flow` branch
- [ ] Get smart contract audit before mainnet deployment
- [ ] Never commit mnemonics to version control

### Best Practices:
- Always set file permissions: `chmod 600 ~/.zeno/wallet.json`
- Rotate test wallets frequently
- Use testnet (Sepolia) for testing
- Never expose RPC URLs in public repositories
- Keep ethers.js and dependencies up to date

---

## Next Steps

After this branch (`blockchain/ethers-integration`), the roadmap includes:

1. **`blockchain/tx-approval-flow`** - User approval UI for transactions
   - Depends on: Ink TUI (`feat/activate-ink-tui`)
   - Depends on: This wallet implementation ✓

2. **`blockchain/sybil-defense`** - Anti-abuse measures
   - Device fingerprinting
   - Rate limiting
   - Email verification

3. **`blockchain/hardware-wallet`** - Hardware wallet support
   - Ledger/Trezor integration
   - Secure signing without key exposure

See `TEAM-BRANCHES.md` for full roadmap.

---

## Questions?

- Check unit tests in `packages/zeno-wallet/src/manager.test.ts`
- Read wallet implementation: `packages/zeno-wallet/src/manager.ts`
- See integration example: `packages/zeno-coding-agent/src/session.ts`
- Review security model in `ZENO-FULL-README.md`

---

**Last Updated:** June 26, 2026  
**Status:** ✓ Complete - blockchain/ethers-integration branch
