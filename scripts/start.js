#!/usr/bin/env node
/**
 * Zeno launcher. Builds the Node packages if needed, then starts the TUI CLI
 * (which in turn spawns the warm Python agent-core). Cross-platform; the
 * primary entry on Windows/macOS/Linux.
 *
 * Pass-through flags, e.g.:  node scripts/start.js --headless --model mock
 */

import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import fs from "node:fs";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const repoRoot = path.resolve(__dirname, "..");
const cliEntry = path.join(repoRoot, "packages", "zeno-tui", "dist", "cli.js");

function run(cmd, args, opts) {
  return new Promise((resolve, reject) => {
    const child = spawn(cmd, args, { stdio: "inherit", shell: false, ...opts });
    child.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`${cmd} exited ${code}`))));
    child.on("error", reject);
  });
}

async function ensureBuilt() {
  if (fs.existsSync(cliEntry)) return;
  process.stderr.write("Building Zeno (first run)...\n");
  const npm = process.platform === "win32" ? "npm.cmd" : "npm";
  await run(npm, ["run", "build"], { cwd: repoRoot });
}

async function main() {
  await ensureBuilt();
  const args = process.argv.slice(2);
  const child = spawn(process.execPath, [cliEntry, ...args], { stdio: "inherit" });
  child.on("exit", (code) => process.exit(code ?? 0));
}

main().catch((err) => {
  process.stderr.write(`launcher failed: ${err?.stack ?? err}\n`);
  process.exit(1);
});
