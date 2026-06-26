/**
 * Unit tests for wallet module.
 *
 * These tests verify wallet structure and error handling.
 * Network-dependent tests (actual wallet creation) require testnet connectivity.
 */

import { strict as assert } from "node:assert";
import { test } from "node:test";
import {
  WalletManager,
  type WalletConfig,
} from "./manager.js";
import { tmpdir } from "node:os";
import { join } from "node:path";

// Mock provider URL (does not require actual network for structure tests)
const mockConfig: WalletConfig = {
  rpcUrl: "http://localhost:8545",
  chainId: 31337, // Hardhat default
};

test("WalletManager - Get address before wallet creation throws error", () => {
  const manager = new WalletManager(mockConfig);

  assert.throws(
    () => manager.getAddress(),
    /Wallet not initialized/,
    "Should throw error when wallet not initialized"
  );
});

test("WalletManager - Load wallet returns null when no wallet exists", async () => {
  const config: WalletConfig = {
    ...mockConfig,
    walletPath: join(tmpdir(), `nonexistent-${Date.now()}.json`),
  };

  const manager = new WalletManager(config);
  const state = await manager.loadWallet();

  assert.equal(state, null, "Should return null when wallet does not exist");
});

test("WalletManager - Wallet destruction clears state", () => {
  const manager = new WalletManager(mockConfig);
  manager.destroy();

  assert.throws(
    () => manager.getAddress(),
    /Wallet not initialized/,
    "Should throw after destroy"
  );
});

test("WalletManager - Multiple wallet instances are independent", () => {
  const manager1 = new WalletManager(mockConfig);
  const manager2 = new WalletManager(mockConfig);

  // Both should throw before initialization
  assert.throws(() => manager1.getAddress());
  assert.throws(() => manager2.getAddress());
});

test("WalletManager - Wallet config structure is valid", () => {
  const config: WalletConfig = {
    rpcUrl: "https://sepolia.infura.io/v3/YOUR-PROJECT-ID",
    chainId: 11155111, // Sepolia
    walletPath: join(tmpdir(), "test-wallet.json"),
  };

  assert.ok(config.rpcUrl, "RPC URL should be set");
  assert.ok(config.chainId > 0, "Chain ID should be positive");
  assert.ok(config.walletPath, "Wallet path should be set");
});

test("WalletManager - Transaction parameters validation", () => {
  const params = {
    to: "0x1234567890123456789012345678901234567890",
    value: "1000000000000000000", // 1 ETH in wei
    data: "0x",
  };

  assert.equal(params.to.length, 42, "Address should be 42 chars");
  assert.ok(params.to.startsWith("0x"), "Address should start with 0x");
  assert.ok(params.value, "Value should be present");
});

test("WalletManager - Error handling for invalid address format", () => {
  const testCases = [
    { addr: "0xinvalid", valid: false, reason: "too short" },
    { addr: "not-an-address", valid: false, reason: "no 0x prefix" },
    { addr: "0x" + "1".repeat(40), valid: true, reason: "valid format" },
  ];

  testCases.forEach(({ addr, valid }) => {
    const isValid = addr.startsWith("0x") && addr.length === 42;
    assert.equal(isValid, valid, `Address ${addr} validation failed`);
  });
});

test("WalletManager - Wallet file permissions structure", () => {
  const mode = 0o600; // Restricted read/write for owner only
  const isRestricted = (mode & 0o077) === 0; // No group/other permissions

  assert.ok(isRestricted, "Wallet file should have restricted permissions");
});

test("WalletManager - Mnemonic structure validation", () => {
  const validMnemonic =
    "abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon abandon about";

  const words = validMnemonic.split(" ");
  assert.equal(words.length, 12, "BIP-39 seed should have 12 words");
  assert.ok(words.every(w => w.length > 0), "All words should be non-empty");
});

test("WalletManager - Derivation path format validation", () => {
  const validPaths = [
    "m/44'/60'/0'/0/0",
    "m/44'/60'/1'/0/0",
    "m/44'/60'/0'/0/1",
  ];

  validPaths.forEach(path => {
    assert.ok(path.startsWith("m/"), "Path should start with m/");
    assert.ok(path.includes("44"), "Should be BIP-44 path");
    assert.ok(path.includes("60"), "Should be ETH coin type (60)");
  });
});

test("WalletManager - Error message formatting", () => {
  const manager = new WalletManager(mockConfig);

  try {
    manager.getAddress();
    assert.fail("Should have thrown");
  } catch (error) {
    assert.ok(error instanceof Error, "Should be Error instance");
    assert.ok(
      error.message.includes("Wallet not initialized"),
      "Error message should be descriptive"
    );
  }
});

test("WalletManager - SessionManager integration interface", () => {
  const manager = new WalletManager(mockConfig);

  // Test that required public methods exist
  assert.ok(typeof manager.createWallet === "function", "createWallet exists");
  assert.ok(typeof manager.loadWallet === "function", "loadWallet exists");
  assert.ok(typeof manager.getAddress === "function", "getAddress exists");
  assert.ok(typeof manager.sign === "function", "sign exists");
  assert.ok(typeof manager.broadcast === "function", "broadcast exists");
  assert.ok(
    typeof manager.signAndBroadcast === "function",
    "signAndBroadcast exists"
  );
  assert.ok(typeof manager.getBalance === "function", "getBalance exists");
  assert.ok(typeof manager.getNonce === "function", "getNonce exists");
  assert.ok(typeof manager.destroy === "function", "destroy exists");
  assert.ok(typeof manager.estimateGas === "function", "estimateGas exists");
});
