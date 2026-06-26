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
  private closed = false;
  private sigintHandler: (() => void) | null = null;
  private completions: string[] = [];

  constructor(opts: { color?: boolean } = {}) {
    this.useColor = opts.color ?? process.stdout.isTTY ?? false;
  }

  private paint(code: string, text: string): string {
    return color(this.useColor, code, text);
  }

  setCompletions(completions: string[]): void {
    this.completions = completions;
  }

  start(): void {
    this.rl = readline.createInterface({
      input: process.stdin,
      output: process.stdout,
      terminal: true,
      prompt: "",
      completer: (line: string) => {
        const matches = this.completions.filter((c) => c.startsWith(line));
        return [matches, line];
      },
    });
    this.rl.on("close", () => {
      this.closed = true;
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

  async requestPermission(message: string): Promise<boolean> {
    process.stdout.write(
      this.paint(C.yellow, `permission needed: ${message}\nallow? [y/N] `),
    );
    return new Promise((resolve) => {
      this.rl?.question("", (answer) => {
        resolve(answer !== null && /^y(es)?$/i.test(answer.trim()));
      });
    });
  }

  async prompt(): Promise<string | null> {
    return new Promise((resolve) => {
      if (!this.rl) return resolve(null);
      
      this.rl.setPrompt(this.promptText());
      this.rl.prompt();
      
      const lineHandler = (answer: string) => {
        this.rl?.removeListener("line", lineHandler);
        const trimmed = answer.trim();
        if (trimmed === "/exit" || trimmed === "/quit") resolve(null);
        else resolve(answer);
      };
      
      this.rl.on("line", lineHandler);
    });
  }

  displaySuggestions(suggestions: string[]): void {
    if (suggestions.length === 0) return;
    const text = suggestions.map((s, i) => `  ${i + 1}. ${s}`).join("\n");
    process.stdout.write(this.paint(C.dim, `\n${text}\n`));
  }

  async selectFromList(items: string[], title?: string): Promise<string | null> {
    if (items.length === 0) return null;
    
    return new Promise((resolve) => {
      let selected = 0;
      const menuHeight = items.length + (title ? 3 : 0) + 3;
      
      const displayMenu = (isUpdate = false) => {
        if (isUpdate) {
          // Move cursor up to overwrite previous menu
          process.stdout.write(`\u001b[${menuHeight}A`); // Move up
          process.stdout.write("\u001b[0J"); // Clear from cursor to end of screen
        }
        
        if (title) {
          process.stdout.write(this.paint(C.cyan, `${title}\n`));
          process.stdout.write(this.paint(C.dim, "─".repeat(60) + "\n"));
        }
        
        items.forEach((item, i) => {
          if (i === selected) {
            process.stdout.write(this.paint(C.bold + C.cyan, `❯ ${item}\n`));
          } else {
            process.stdout.write(`  ${item}\n`);
          }
        });
        
        process.stdout.write(this.paint(C.dim, "(↑↓ arrows, Enter to select, Esc to cancel)\n"));
      };
      
      // Display initial menu
      displayMenu(false);
      
      // Handle keyboard input
      const stdin = process.stdin;
      stdin.setRawMode?.(true);
      stdin.resume();
      stdin.setEncoding("utf8");
      
      const onKeyPress = (key: string) => {
        if (key === "\u001b[A") {
          // Up arrow
          selected = (selected - 1 + items.length) % items.length;
          displayMenu(true);
        } else if (key === "\u001b[B") {
          // Down arrow
          selected = (selected + 1) % items.length;
          displayMenu(true);
        } else if (key === "\r" || key === "\n") {
          // Enter - select current item
          stdin.setRawMode?.(false);
          stdin.removeListener("data", onKeyPress);
          process.stdout.write(this.paint(C.green, `✓ Selected: ${items[selected]}\n`));
          resolve(items[selected]);
        } else if (key === "\u001b") {
          // Escape
          stdin.setRawMode?.(false);
          stdin.removeListener("data", onKeyPress);
          // Clear the menu display
          process.stdout.write(`\u001b[${menuHeight}A`);
          process.stdout.write("\u001b[0J");
          resolve(null);
        }
      };
      
      stdin.on("data", onKeyPress);
    });
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
