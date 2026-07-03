// packages/zeno-wallet/src/demo.ts
import { WalletManager } from "./manager.js";
import { ethers } from "ethers";
import { readFileSync, unlinkSync, existsSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

async function main() {
  console.log("🚀 Starting Zeno Wallet Live Demo...\n");

  // 1. Setup local environment
  const walletPath = join(tmpdir(), `zeno-demo-wallet-${Date.now()}.json`);
  const encryptionKey = "super-secret-demo-password-123";
  
  // Connect to local Hardhat node (default port 8545)
  const provider = new ethers.JsonRpcProvider("http://127.0.0.1:8545");
  
  // Get a pre-funded Hardhat account to fund our new wallet
  // This is Hardhat's default Account #0 private key
  const funder = new ethers.Wallet(
    "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80",
    provider
  );

  const manager = new WalletManager({
    rpcUrl: "http://127.0.0.1:8545",
    chainId: 31337, // Hardhat default chain ID
    walletPath,
    encryptionKey,
  });

  try {
    // 2. Create Wallet & Test Encryption
    console.log("1️⃣ Creating new wallet and saving to disk...");
    const state = await manager.createWallet();
    console.log(`✅ Wallet created! Address: ${state.address}`);
    
    // Verify encryption on disk
    const rawFileContent = readFileSync(walletPath, "utf-8");
    const isEncrypted = !rawFileContent.includes(state.mnemonic);
    console.log(`🔒 Is wallet file encrypted on disk? ${isEncrypted ? "YES ✅" : "NO ❌"}`);
    if (!isEncrypted) {
        console.log("⚠️ Raw content snippet:", rawFileContent.substring(0, 100) + "...");
    }

    // 3. Load Wallet & Test Decryption
    console.log("\n2️⃣ Loading wallet from encrypted disk...");
    const manager2 = new WalletManager({
      rpcUrl: "http://127.0.0.1:8545",
      chainId: 31337,
      walletPath,
      encryptionKey,
    });
    const loadedState = await manager2.loadWallet();
    console.log(`✅ Wallet loaded! Address matches: ${loadedState?.address === state.address ? "YES ✅" : "NO ❌"}`);

    // 4. Fund the wallet
    console.log("\n3️⃣ Funding wallet from local Hardhat account...");
    const fundTx = await funder.sendTransaction({
      to: state.address,
      value: ethers.parseEther("10.0"),
    });
    await fundTx.wait();
    const balance = await manager2.getBalance();
    console.log(`✅ Wallet funded! Balance: ${ethers.formatEther(balance)} ETH`);

    // 5. Send a standard transaction
    console.log("\n4️⃣ Sending a standard transaction...");
    const result = await manager2.signAndBroadcast({
      to: funder.address,
      value: ethers.parseEther("1.0").toString(),
    });
    console.log(`✅ Transaction sent! Hash: ${result.txHash}, Success: ${result.success}`);

    // 6. Test Nonce Management (Rapid Transactions)
    console.log("\n5️⃣ Testing rapid transactions (Nonce Management Fix)...");
    const rapidTxs = [];
    for (let i = 0; i < 3; i++) {
      // Fire them off without waiting for the previous one to mine
      const txPromise = manager2.signAndBroadcast({
        to: funder.address,
        value: ethers.parseEther("0.1").toString(),
      });
      rapidTxs.push(txPromise);
    }
    
    const results = await Promise.all(rapidTxs);
    const allSuccess = results.every(r => r.success);
    console.log(`✅ Rapid transactions completed! All successful: ${allSuccess ? "YES ✅" : "NO ❌"}`);
    results.forEach((r, i) => console.log(`   Tx ${i+1}: ${r.txHash}`));

    // 7. Final Balance Check
    const finalBalance = await manager2.getBalance();
    console.log(`\n🏁 Final Balance: ${ethers.formatEther(finalBalance)} ETH`);

  } catch (error) {
    console.error("❌ Demo failed:", error);
  } finally {
    // Cleanup
    if (existsSync(walletPath)) {
      unlinkSync(walletPath);
    }
    manager.destroy();
    console.log("\n🧹 Cleaned up demo files.");
  }
}

main().catch(console.error);