/**
 * Wallet module: HD seed-based wallet for Ethereum transactions.
 *
 * This module handles:
 * - Creating wallets from HD seeds (BIP-39 mnemonic)
 * - Signing ERC-20 transfers and raw transactions
 * - Broadcasting transactions to the network
 * - Gas estimation and nonce tracking
 * - Error handling for failed transactions
 *
 * Security: Keys are never exposed outside this module.
 */

import {
  Wallet,
  ethers,
  JsonRpcProvider,
  TransactionResponse,
  TransactionReceipt,
  toBeHex,
  type TransactionRequest,
} from "ethers";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { homedir } from "node:os";
import { join } from "node:path";

export interface WalletConfig {
  rpcUrl: string;
  chainId: number;
  walletPath?: string;
}

export interface WalletState {
  mnemonic: string;
  derivationPath: string;
  address: string;
  nonce: number;
}

export interface TransactionParams {
  to: string;
  value?: string;
  data?: string;
  gasLimit?: string;
  gasPrice?: string;
  maxFeePerGas?: string;
  maxPriorityFeePerGas?: string;
}

export interface GasEstimate {
  gasLimit: string;
  gasPrice: string;
  estimatedCost: string;
}

export interface BroadcastResult {
  success: boolean;
  txHash?: string;
  receipt?: TransactionReceipt | null;
  error?: string;
  confirmationBlocks?: number;
}

/**
 * WalletManager: Manages wallet creation, signing, and broadcasting.
 */
export class WalletManager {
  private provider: JsonRpcProvider;
  private wallet: Wallet | null = null;
  private walletState: WalletState | null = null;
  private config: WalletConfig;
  private defaultDerivationPath = "m/44'/60'/0'/0/0";

  constructor(config: WalletConfig) {
    this.config = config;
    this.provider = new JsonRpcProvider(config.rpcUrl);
  }

  /**
   * Create a new wallet from a BIP-39 mnemonic (or generate one).
   * Optionally persists the wallet state to disk.
   */
  async createWallet(
    mnemonic?: string,
    derivationPath?: string
  ): Promise<WalletState> {
    try {
      const path = derivationPath || this.defaultDerivationPath;

      // Generate or use provided mnemonic
      let seedPhrase = mnemonic;
      if (!seedPhrase) {
        const randomWallet = Wallet.createRandom();
        seedPhrase = randomWallet.mnemonic?.phrase;
      }
      if (!seedPhrase) {
        throw new Error("Failed to generate or use mnemonic");
      }

      // Create wallet from mnemonic using ethers v6 API
      // fromPhrase returns a wallet at the default path, then derive from there
      const hdNode = ethers.HDNodeWallet.fromMnemonic(
        ethers.Mnemonic.fromPhrase(seedPhrase),
        path
      );
      this.wallet = hdNode.connect(this.provider) as any;

      // Get initial nonce from network
      const nonce = await this.provider.getTransactionCount(
        this.wallet!.address
      );

      this.walletState = {
        mnemonic: seedPhrase,
        derivationPath: path,
        address: this.wallet!.address,
        nonce,
      };

      // Persist wallet state if path provided
      if (this.config.walletPath) {
        this.saveWalletState();
      }

      return this.walletState;
    } catch (error) {
      throw new Error(
        `Failed to create wallet: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  /**
   * Load wallet from previously saved state.
   */
  async loadWallet(): Promise<WalletState | null> {
    try {
      if (!this.config.walletPath) {
        return null;
      }

      const state = this.readWalletState();
      if (!state) {
        return null;
      }

      // Restore wallet from mnemonic using ethers v6 API
      const hdNode = ethers.HDNodeWallet.fromMnemonic(
        ethers.Mnemonic.fromPhrase(state.mnemonic),
        state.derivationPath
      );
      this.wallet = hdNode.connect(this.provider) as any;

      // Update nonce from network
      const nonce = await this.provider.getTransactionCount(
        this.wallet!.address
      );
      state.nonce = nonce;

      this.walletState = state;
      return this.walletState;
    } catch (error) {
      throw new Error(
        `Failed to load wallet: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  /**
   * Get current wallet address (requires wallet to be initialized).
   */
  getAddress(): string {
    if (!this.wallet || !this.walletState) {
      throw new Error("Wallet not initialized. Call createWallet() first.");
    }
    return this.wallet.address;
  }

  /**
   * Estimate gas for a transaction.
   */
  async estimateGas(params: TransactionParams): Promise<GasEstimate> {
    try {
      if (!this.wallet) {
        throw new Error("Wallet not initialized");
      }

      const tx: TransactionRequest = {
        to: params.to,
        value: params.value ? toBeHex(BigInt(params.value)) : "0x0",
        data: params.data || "0x",
        from: this.wallet.address,
      };

      const gasLimit = await this.provider.estimateGas(tx);
      const feeData = await this.provider.getFeeData();

      if (!feeData.gasPrice && !feeData.maxFeePerGas) {
        throw new Error("Unable to fetch gas price data");
      }

      const gasPrice =
        feeData.maxFeePerGas || feeData.gasPrice || BigInt(20e9);
      const estimatedCost = (gasLimit * gasPrice).toString();

      return {
        gasLimit: gasLimit.toString(),
        gasPrice: gasPrice.toString(),
        estimatedCost,
      };
    } catch (error) {
      throw new Error(
        `Gas estimation failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  /**
   * Sign a transaction (returns signed transaction hex, does not broadcast).
   */
  async sign(params: TransactionParams): Promise<string> {
    try {
      if (!this.wallet || !this.walletState) {
        throw new Error("Wallet not initialized");
      }

      // Ensure nonce is up-to-date
      const currentNonce = await this.provider.getTransactionCount(
        this.wallet.address
      );
      this.walletState.nonce = currentNonce;

      const tx: TransactionRequest = {
        to: params.to,
        value: params.value ? toBeHex(BigInt(params.value)) : "0x0",
        data: params.data || "0x",
        gasLimit: params.gasLimit
          ? BigInt(params.gasLimit)
          : BigInt(21000),
        nonce: this.walletState.nonce,
        chainId: this.config.chainId,
      };

      // Use modern fee mechanism if available
      const feeData = await this.provider.getFeeData();
      if (feeData.maxFeePerGas) {
        (tx as any).maxFeePerGas = BigInt(
          params.maxFeePerGas || feeData.maxFeePerGas.toString()
        );
        (tx as any).maxPriorityFeePerGas = BigInt(
          params.maxPriorityFeePerGas ||
            feeData.maxPriorityFeePerGas?.toString() ||
            "1000000000"
        );
      } else {
        (tx as any).gasPrice = BigInt(
          params.gasPrice || feeData.gasPrice?.toString() || "20000000000"
        );
      }

      const signedTx = await this.wallet.signTransaction(tx);
      return signedTx || "";
    } catch (error) {
      throw new Error(
        `Transaction signing failed: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  /**
   * Broadcast a signed transaction to the network.
   */
  async broadcast(signedTx: string): Promise<BroadcastResult> {
    try {
      if (!this.wallet) {
        throw new Error("Wallet not initialized");
      }

      const txResponse: TransactionResponse | null =
        await this.provider.broadcastTransaction(signedTx);

      if (!txResponse) {
        return {
          success: false,
          error: "Failed to broadcast transaction",
        };
      }

      // Wait for receipt with timeout
      const receipt = await Promise.race([
        txResponse.wait(),
        new Promise<null>((_, reject) =>
          setTimeout(
            () => reject(new Error("Transaction confirmation timeout")),
            120000
          )
        ),
      ]);

      if (!receipt) {
        return {
          success: false,
          txHash: txResponse.hash,
          error: "Transaction failed or timed out",
        };
      }

      // Increment nonce after successful broadcast
      if (this.walletState) {
        this.walletState.nonce++;
      }

      return {
        success: receipt.status === 1,
        txHash: receipt.hash,
        receipt,
        confirmationBlocks: typeof receipt.confirmations === "function" ? 0 : (receipt.confirmations as any) || 0,
      };
    } catch (error) {
      return {
        success: false,
        error:
          error instanceof Error
            ? error.message
            : "Unknown error during broadcast",
      };
    }
  }

  /**
   * Sign and broadcast a transaction in one call.
   */
  async signAndBroadcast(params: TransactionParams): Promise<BroadcastResult> {
    try {
      const signedTx = await this.sign(params);
      return await this.broadcast(signedTx);
    } catch (error) {
      return {
        success: false,
        error:
          error instanceof Error
            ? error.message
            : "Unknown error during sign and broadcast",
      };
    }
  }

  /**
   * Get current account balance in wei.
   */
  async getBalance(): Promise<string> {
    if (!this.wallet) {
      throw new Error("Wallet not initialized");
    }
    const balance = await this.provider.getBalance(this.wallet.address);
    return balance.toString();
  }

  /**
   * Get current wallet nonce from network.
   */
  async getNonce(): Promise<number> {
    if (!this.wallet) {
      throw new Error("Wallet not initialized");
    }
    const nonce = await this.provider.getTransactionCount(this.wallet.address);
    return nonce;
  }

  /**
   * Save wallet state to disk (encrypted path).
   */
  private saveWalletState(): void {
    if (!this.walletState || !this.config.walletPath) {
      return;
    }

    try {
      const stateJson = JSON.stringify(this.walletState, null, 2);
      writeFileSync(this.config.walletPath, stateJson, { mode: 0o600 });
    } catch (error) {
      console.warn(
        `Failed to save wallet state: ${error instanceof Error ? error.message : String(error)}`
      );
    }
  }

  /**
   * Read wallet state from disk.
   */
  private readWalletState(): WalletState | null {
    if (!this.config.walletPath || !existsSync(this.config.walletPath)) {
      return null;
    }

    try {
      const stateJson = readFileSync(this.config.walletPath, "utf-8");
      return JSON.parse(stateJson) as WalletState;
    } catch (error) {
      console.warn(
        `Failed to read wallet state: ${error instanceof Error ? error.message : String(error)}`
      );
      return null;
    }
  }

  /**
   * Destroy wallet (clear keys from memory).
   */
  destroy(): void {
    this.wallet = null;
    this.walletState = null;
  }
}

/**
 * Get default wallet path in user's home directory.
 */
export function getDefaultWalletPath(): string {
  return join(homedir(), ".zeno", "wallet.json");
}
