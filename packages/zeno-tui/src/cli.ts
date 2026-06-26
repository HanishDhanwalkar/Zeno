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

interface ModelConfig {
  id: string;
  name: string;
  description: string;
}

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

let modelsConfig: ModelConfig[] = [];

function loadModelsConfig(): void {
  try {
    const configPath = path.join(import.meta.dirname ?? process.cwd(), "models.json");
    const content = fs.readFileSync(configPath, "utf8");
    const parsed = JSON.parse(content) as { models: ModelConfig[] };
    modelsConfig = parsed.models;
  } catch (err) {
    modelsConfig = [
      {
        id: "mock",
        name: "Mock (Offline)",
        description: "Offline mock provider for testing",
      },
    ];
  }
}

function getModelsConfigPath(): string {
  return path.join(import.meta.dirname ?? process.cwd(), "models.json");
}

function saveModelsConfig(): boolean {
  try {
    const configPath = getModelsConfigPath();
    fs.writeFileSync(configPath, JSON.stringify({ models: modelsConfig }, null, 2), "utf8");
    return true;
  } catch {
    return false;
  }
}

function parseArgs(argv: string[]): CliArgs {
  const args: CliArgs = {
    model: process.env.ZENO_MODEL ?? "mock",
    headless: true,
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

const COMMANDS = [
  { name: "model", description: "Change the current model" },
  { name: "clear", description: "Clear session history" },
  { name: "config", description: "Edit models configuration" },
  { name: "help", description: "Show available commands" },
];

function getCommandSuggestions(prefix: string): string[] {
  return COMMANDS.filter((c) => c.name.startsWith(prefix))
    .map((c) => `/${c.name} — ${c.description}`);
}

function getModelSuggestions(prefix: string): string[] {
  return modelsConfig
    .filter((m) => m.id.toLowerCase().startsWith(prefix.toLowerCase()))
    .map((m) => `${m.id} (${m.name})`);
}

function getAllCompletions(): string[] {
  const completions: string[] = [];
  
  // Add all commands
  COMMANDS.forEach((c) => {
    completions.push(`/${c.name}`);
  });
  
  // Add all models with /model prefix
  modelsConfig.forEach((m) => {
    completions.push(`/model ${m.id}`);
  });
  
  return completions;
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

async function handleConfigCommand(renderer: Renderer): Promise<void> {
  renderer.addMessage("system", "Models Configuration:");
  renderer.addMessage("system", "─".repeat(60));
  
  modelsConfig.forEach((m, i) => {
    renderer.addMessage("system", `${i + 1}. ${m.id}`);
    renderer.addMessage("system", `   Name: ${m.name}`);
    renderer.addMessage("system", `   Desc: ${m.description}`);
  });
  
  renderer.addMessage("system", "");
  renderer.addMessage("system", "To edit, modify: " + getModelsConfigPath());
  renderer.addMessage("system", "Format: JSON with 'models' array containing {id, name, description}");
}

async function pickRenderer(headless: boolean): Promise<Renderer> {
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
  loadModelsConfig();

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
  renderer.setCompletions(getAllCompletions());
  renderer.setStatusLine(status());

  while (true) {
    const input = await renderer.prompt();
    if (input === null) break;
    if (!input.trim()) continue;

    // Handle slash commands
    if (input.startsWith("/")) {
      const fullInput = input.slice(1);
      const parts = fullInput.split(/\s+/);
      const command = parts[0];
      const rest = parts.slice(1).join(" ");

      if (command === "") {
        renderer.displaySuggestions(getCommandSuggestions(""));
        continue;
      } else if (command === "help") {
        const allCommands = COMMANDS.map((c) => `  /${c.name} — ${c.description}`);
        renderer.error(`Available commands:\n${allCommands.join("\n")}`);
        continue;
      } else if (command === "model") {
        if (rest === "") {
          renderer.addMessage("system", `Current model: ${args.model}`);
          const models = modelsConfig.map((m) => `${m.id} (${m.name})`);
          const selected = await renderer.selectFromList(models, "Available Models:");
          if (selected) {
            const modelId = selected.split(" (")[0];
            args.model = modelId;
            session.model = modelId;
            renderer.addMessage("system", `Model changed to: ${modelId}`);
            renderer.setStatusLine(status());
          }
          continue;
        } else {
          args.model = rest;
          session.model = rest;
          renderer.addMessage("system", `Model changed to: ${rest}`);
          renderer.setStatusLine(status());
          continue;
        }
      } else if (command === "clear") {
        session.messages = session.messages.filter((m) => m.role === "system");
        renderer.error(`Session history cleared. ${session.messages.length} message(s) remaining.`);
        renderer.setStatusLine(status());
        continue;
      } else if (command === "config") {
        await handleConfigCommand(renderer);
        continue;
      } else {
        // Show suggestions for partial commands
        const suggestions = getCommandSuggestions(command);
        if (suggestions.length > 0) {
          renderer.displaySuggestions(suggestions);
        } else {
          renderer.error(`Unknown command: /${command}`);
        }
        continue;
      }
    }

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
