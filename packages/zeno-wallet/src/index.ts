/**
 * Zeno Wallet: HD seed-based Ethereum wallet for transaction signing and broadcasting.
 *
 * Independent blockchain package for secure wallet management.
 * 
 * This module provides complete wallet functionality:
 * - HD wallet creation and restoration (BIP-39 mnemonics, BIP-44 derivation)
 * - Transaction signing with proper nonce management
 * - Gas estimation with EIP-1559 support
 * - Transaction broadcasting to the network
 * - Secure wallet state persistence
 *
 * Security model:
 * - Keys are never exposed outside this module
 * - Wallet state persisted with restricted file permissions (0o600)
 * - Designed for isolated wallet process via IPC (future hardening)
 * - No dependencies on session or agent logic
 *
 * Usage:
 *   import { WalletManager } from '@zeno/wallet';
 *   
 *   const manager = new WalletManager({
 *     rpcUrl: "https://sepolia.infura.io/v3/YOUR-PROJECT-ID",
 *     chainId: 11155111,
 *     walletPath: "~/.zeno/wallet.json"
 *   });
 *   
 *   // Create new wallet
 *   await manager.createWallet();
 *   
 *   // Or restore existing
 *   await manager.loadWallet();
 *   
 *   // Sign and broadcast transaction
 *   const result = await manager.signAndBroadcast({
 *     to: "0x...",
 *     value: "1000000000000000000" // 1 ETH in wei
 *   });
 */

export {
  WalletManager,
  getDefaultWalletPath,
} from "./manager.js";

export type {
  WalletConfig,
  WalletState,
  TransactionParams,
  GasEstimate,
  BroadcastResult,
} from "./manager.js";
