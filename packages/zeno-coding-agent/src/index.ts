/**
 * Public API for zeno-coding-agent.
 */

import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";
import { RpcClient, type RpcClientOptions } from "./rpcClient.js";

export * from "./protocol.js";
export { RpcClient } from "./rpcClient.js";
export type { RpcClientOptions } from "./rpcClient.js";
export { SessionManager } from "./session.js";
export type {
  SessionOptions,
  SessionCallbacks,
  PermissionPrompt,
} from "./session.js";
export { prune, DEFAULT_PROTECTED_TOKENS } from "./prune.js";
export { classify } from "./permission.js";
export type { Classification, Verdict } from "./permission.js";
export { countTokens, countMessageTokens } from "./tokens.js";
// Re-export wallet types for convenience (but don't re-export the class)
// Users should import WalletManager directly from @zeno/wallet
export type {
  WalletConfig,
  WalletState,
  TransactionParams,
  GasEstimate,
  BroadcastResult,
} from "@zeno/wallet";

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** Locate the repo root (the directory containing `packages/`). */
export function findRepoRoot(start: string = __dirname): string {
  let dir = start;
  for (let i = 0; i < 8; i++) {
    if (fs.existsSync(path.join(dir, "packages", "zeno-agent-core"))) return dir;
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  // Fallback: dist is at packages/zeno-coding-agent/dist
  return path.resolve(__dirname, "..", "..", "..");
}

export interface AgentCoreClientOptions {
  pythonPath?: string;
  repoRoot?: string;
  env?: NodeJS.ProcessEnv;
}

/** Build an RpcClient configured to launch the Python agent-core. */
export function createAgentCoreClient(opts: AgentCoreClientOptions = {}): RpcClient {
  const repoRoot = opts.repoRoot ?? findRepoRoot();
  const agentCoreDir = path.join(repoRoot, "packages", "zeno-agent-core");
  const python = opts.pythonPath ?? process.env.ZENO_PYTHON ?? "python";

  const rpcOpts: RpcClientOptions = {
    command: python,
    args: ["-m", "zeno_agent_core.main"],
    cwd: agentCoreDir,
    env: { ...process.env, PYTHONUNBUFFERED: "1", ...opts.env },
  };
  return new RpcClient(rpcOpts);
}
