/**
 * Zero-dependency renderer built on node:readline.
 *
 * Serves as the default fallback when Ink isn't available and as the
 * `--headless` implementation. Proves the Renderer interface is sufficient
 * without any UI framework.
 */

import readline from "node:readline";
import type { Renderer } from "./renderer.js";
import type { ToolResult } from "zeno-coding-agent";

const C = {
  reset: "\x1b[0m",
  dim: "\x1b[2m",
  bold: "\x1b[1m",
  cyan: "\x1b[36m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  red: "\x1b[31m",
  magenta: "\x1b[35m",
};

function color(on: boolean, code: string, text: string): string {
  return on ? `${code}${text}${C.reset}` : text;
}

export class PlainRenderer implements Renderer {
  private rl: readline.Interface | null = null;
  private streaming = false;
  private readonly useColor: boolean;
  private status = "";
  private cancelHandler: (() => void) | null = null;
  private lineQueue: string[] = [];
  private lineWaiters: ((v: string | null) => void)[] = [];
  private closed = false;
  private sigintHandler: (() => void) | null = null;

  constructor(opts: { color?: boolean } = {}) {
    this.useColor = opts.color ?? process.stdout.isTTY ?? false;
  }

  private paint(code: string, text: string): string {
    return color(this.useColor, code, text);
  }

  start(): void {
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: false,
    });
    this.rl.on("line", (line) => {
      const waiter = this.lineWaiters.shift();
      if (waiter) waiter(line);
      else this.lineQueue.push(line);
    });
    this.rl.on("close", () => {
      this.closed = true;
      while (this.lineWaiters.length) this.lineWaiters.shift()!(null);
    });
    this.sigintHandler = () => {
      if (this.streaming && this.cancelHandler) {
        this.cancelHandler();
      } else {
        this.stop();
        process.exit(0);
      }
    };
    process.on("SIGINT", this.sigintHandler);
    process.stdout.write(
      this.paint(C.bold, "Zeno") +
        this.paint(C.dim, "  ultra-lean AI coding harness\n") +
        this.paint(C.dim, "Type your message. /exit to quit, Ctrl+C to cancel.\n\n"),
    );
  }

  onCancel(handler: () => void): void {
    this.cancelHandler = handler;
  }

  addMessage(role: "user" | "assistant" | "system", text: string): void {
    const label =
      role === "user"
        ? this.paint(C.cyan, "you")
        : role === "assistant"
          ? this.paint(C.green, "zeno")
          : this.paint(C.dim, "system");
    process.stdout.write(`${label}: ${text}\n`);
  }

  beginAssistant(): void {
    this.streaming = true;
    process.stdout.write(this.paint(C.green, "zeno") + ": ");
  }

  appendAssistant(text: string): void {
    process.stdout.write(text);
  }

  endAssistant(): void {
    if (this.streaming) process.stdout.write("\n");
    this.streaming = false;
  }

  toolCall(name: string, args: Record<string, unknown>): void {
    if (this.streaming) {
      process.stdout.write("\n");
      this.streaming = false;
    }
    const argStr = JSON.stringify(args);
    process.stdout.write(
      this.paint(C.magenta, `  - ${name}`) + this.paint(C.dim, ` ${argStr}\n`),
    );
  }

  toolResult(name: string, result: ToolResult): void {
    if (result.error) {
      process.stdout.write(this.paint(C.red, `  x ${name}: ${result.error}\n`));
      return;
    }
    const firstLine = (result.output ?? "").split("\n")[0] ?? "";
    const preview =
      firstLine.length > 80 ? firstLine.slice(0, 77) + "..." : firstLine;
    const extra = result.truncated ? " (truncated)" : "";
    process.stdout.write(this.paint(C.dim, `  ok ${name}: ${preview}${extra}\n`));
  }

  error(message: string): void {
    if (this.streaming) {
      process.stdout.write("\n");
      this.streaming = false;
    }
    process.stdout.write(this.paint(C.red, `error: ${message}\n`));
  }

  setStatusLine(text: string): void {
    this.status = text;
    if (this.rl) this.rl.setPrompt(this.promptText());
  }

  private promptText(): string {
    const status = this.status ? this.paint(C.dim, `[${this.status}] `) : "";
    return `${status}${this.paint(C.cyan, "you")}: `;
  }

  private readLine(): Promise<string | null> {
    const queued = this.lineQueue.shift();
    if (queued !== undefined) return Promise.resolve(queued);
    if (this.closed) return Promise.resolve(null);
    return new Promise((resolve) => this.lineWaiters.push(resolve));
  }

  async requestPermission(message: string): Promise<boolean> {
    process.stdout.write(
      this.paint(C.yellow, `permission needed: ${message}\nallow? [y/N] `),
    );
    const answer = await this.readLine();
    return answer !== null && /^y(es)?$/i.test(answer.trim());
  }

  async prompt(): Promise<string | null> {
    process.stdout.write(this.promptText());
    const answer = await this.readLine();
    if (answer === null) return null;
    const trimmed = answer.trim();
    if (trimmed === "/exit" || trimmed === "/quit") return null;
    return answer;
  }

  stop(): void {
    if (this.sigintHandler) {
      process.off("SIGINT", this.sigintHandler);
      this.sigintHandler = null;
    }
    this.rl?.close();
    this.rl = null;
  }
}
