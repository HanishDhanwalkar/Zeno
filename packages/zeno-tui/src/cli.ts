/**
 * Zeno CLI entry point.
 *
 * Wires the renderer (Ink or plain), the Python agent-core client, and the
 * session manager into a simple multi-turn REPL. Everything UI-related goes
 * through the Renderer interface.
 */

import fs from "node:fs";
import path from "node:path";
import { once } from "node:events";
import {
  createAgentCoreClient,
  SessionManager,
  findRepoRoot,
  type RpcClient,
} from "zeno-coding-agent";
import type { Renderer } from "./renderer.js";
import { PlainRenderer } from "./plainRenderer.js";

const SYSTEM_PROMPT = [
  "You are Zeno, an ultra-lean AI coding agent.",
  "You have exactly four tools: read, write, edit, bash.",
  "Prefer reading files before editing. Make minimal, correct changes.",
  "When done, give a short summary.",
].join(" ");

interface CliArgs {
  model: string;
  headless: boolean;
  root: string;
}

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = {
    model: process.env.ZENO_MODEL ?? "mock",
    headless: false,
    root: process.cwd(),
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === "--model" || a === "-m") args.model = argv[++i] ?? args.model;
    else if (a === "--headless") args.headless = true;
    else if (a === "--root") args.root = path.resolve(argv[++i] ?? args.root);
  }
  return args;
}

/** Tiny .env loader (no dependency). Does not overwrite existing env vars. */
function loadEnv(dir: string): void {
  const file = path.join(dir, ".env");
  if (!fs.existsSync(file)) return;
  for (const line of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const m = /^\s*([\w.-]+)\s*=\s*(.*)\s*$/.exec(line);
    if (!m) continue;
    const key = m[1];
    if (process.env[key] !== undefined) continue;
    let val = m[2];
    if (
      (val.startsWith('"') && val.endsWith('"')) ||
      (val.startsWith("'") && val.endsWith("'"))
    ) {
      val = val.slice(1, -1);
    }
    process.env[key] = val;
  }
}

async function pickRenderer(headless: boolean): Promise<Renderer> {
  const canInk = !headless && Boolean(process.stdin.isTTY);
  if (canInk) {
    try {
      const { InkRenderer } = await import("./inkRenderer.js");
      return new InkRenderer();
    } catch (err) {
      process.stderr.write(`(ink unavailable, using plain renderer: ${err})\n`);
    }
  }
  return new PlainRenderer();
}

async function waitReady(client: RpcClient, timeoutMs = 15000): Promise<void> {
  await Promise.race([
    once(client, "ready"),
    new Promise((_, reject) =>
      setTimeout(() => reject(new Error("python agent-core did not become ready")), timeoutMs),
    ),
  ]);
}

async function main(): Promise<void> {
  const args = parseArgs(process.argv.slice(2));
  const repoRoot = findRepoRoot();
  loadEnv(repoRoot);
  loadEnv(args.root);

  const renderer = await pickRenderer(args.headless);

  let shuttingDown = false;
  const client = createAgentCoreClient({ repoRoot });

  let respawns = 0;
  client.on("exit", (code: number | null) => {
    if (shuttingDown) return;
    if (respawns < 2) {
      respawns++;
      renderer.error(`agent-core exited (code ${code}); restarting...`);
      try {
        client.start();
      } catch (err) {
        renderer.error(`restart failed: ${err}`);
      }
    } else {
      renderer.error("agent-core keeps exiting; giving up.");
    }
  });
  client.on("error", (err: Error) => renderer.error(`client error: ${err.message}`));

  client.start();
  try {
    await waitReady(client);
  } catch (err) {
    process.stderr.write(`${err}\n`);
    process.exit(1);
  }

  let assistantOpen = false;
  const ensureAssistant = () => {
    if (!assistantOpen) {
      renderer.beginAssistant();
      assistantOpen = true;
    }
  };
  const closeAssistant = () => {
    if (assistantOpen) {
      renderer.endAssistant();
      assistantOpen = false;
    }
  };

  const session = new SessionManager({
    client,
    projectRoot: args.root,
    model: args.model,
    systemPrompt: SYSTEM_PROMPT,
    callbacks: {
      onTextDelta: (t) => {
        ensureAssistant();
        renderer.appendAssistant(t);
      },
      onToolCall: (p) => {
        closeAssistant();
        renderer.toolCall(p.name, p.args);
      },
      onToolResult: (p) => renderer.toolResult(p.name, p.result),
      onError: (m) => {
        closeAssistant();
        renderer.error(m);
      },
      onStreamEnd: () => {
        closeAssistant();
        renderer.setStatusLine(status());
      },
      onPermissionPrompt: (pr) =>
        renderer.requestPermission(`${pr.name} — ${pr.reason}`),
    },
  });

  const status = () =>
    `${args.model} · ${session.messages.length} msgs · ~${session.tokenCount} tok`;

  renderer.onCancel(() => session.cancel());
  renderer.start();
  renderer.setStatusLine(status());

  while (true) {
    const input = await renderer.prompt();
    if (input === null) break;
    if (!input.trim()) continue;
    renderer.setStatusLine("thinking...");
    await session.sendUserMessage(input);
  }

  shuttingDown = true;
  client.stop();
  renderer.stop();
}

main().catch((err) => {
  process.stderr.write(`fatal: ${err?.stack ?? err}\n`);
  process.exit(1);
});
