/**
 * JSON-RPC 2.0 client that spawns and talks to the Python agent-core over
 * stdio (NDJSON). Node owns the child process lifecycle.
 */

import { spawn, type ChildProcessByStdio } from "node:child_process";
import type { Writable, Readable } from "node:stream";
import { EventEmitter } from "node:events";

type AgentChild = ChildProcessByStdio<Writable, Readable, null>;

export interface RpcClientOptions {
  /** executable to run, e.g. "python" */
  command: string;
  /** args, e.g. ["-m", "zeno_agent_core.main"] */
  args: string[];
  /** working directory for the child (must make the module importable) */
  cwd: string;
  env?: NodeJS.ProcessEnv;
}

interface Pending {
  resolve: (value: unknown) => void;
  reject: (err: Error) => void;
}

/**
 * Emits:
 *   "notification" (method: string, params: any)
 *   "ready"        (params: SystemReadyParams)  — convenience for system/ready
 *   "exit"         (code: number | null, signal: string | null)
 *   "error"        (err: Error)
 */
export class RpcClient extends EventEmitter {
  private child: AgentChild | null = null;
  private buffer = "";
  private nextId = 1;
  private pending = new Map<number, Pending>();
  private readonly opts: RpcClientOptions;

  constructor(opts: RpcClientOptions) {
    super();
    this.opts = opts;
  }

  start(): void {
    const child: AgentChild = spawn(this.opts.command, this.opts.args, {
      cwd: this.opts.cwd,
      env: this.opts.env ?? process.env,
      stdio: ["pipe", "pipe", "inherit"],
    });

    child.stdout.setEncoding("utf8");
    child.stdout.on("data", (chunk: string) => this.onData(chunk));
    child.on("exit", (code, signal) => {
      this.rejectAllPending(new Error(`python exited (code=${code}, signal=${signal})`));
      this.emit("exit", code, signal);
    });
    child.on("error", (err) => this.emit("error", err));
    this.child = child;
  }

  private onData(chunk: string): void {
    this.buffer += chunk;
    let idx: number;
    while ((idx = this.buffer.indexOf("\n")) >= 0) {
      const line = this.buffer.slice(0, idx).trim();
      this.buffer = this.buffer.slice(idx + 1);
      if (line) this.handleLine(line);
    }
  }

  private handleLine(line: string): void {
    let msg: any;
    try {
      msg = JSON.parse(line);
    } catch {
      this.emit("error", new Error(`invalid JSON from python: ${line}`));
      return;
    }

    if (typeof msg.id !== "undefined" && msg.id !== null && msg.method === undefined) {
      // response to one of our requests
      const pending = this.pending.get(msg.id);
      if (!pending) return;
      this.pending.delete(msg.id);
      if (msg.error) {
        pending.reject(new Error(msg.error.message ?? "rpc error"));
      } else {
        pending.resolve(msg.result);
      }
      return;
    }

    if (typeof msg.method === "string") {
      this.emit("notification", msg.method, msg.params ?? {});
      if (msg.method === "system/ready") this.emit("ready", msg.params ?? {});
    }
  }

  sendRequest<T = unknown>(method: string, params: unknown): Promise<T> {
    if (!this.child) return Promise.reject(new Error("rpc client not started"));
    const id = this.nextId++;
    const payload = JSON.stringify({ jsonrpc: "2.0", id, method, params }) + "\n";
    return new Promise<T>((resolve, reject) => {
      this.pending.set(id, { resolve: resolve as (v: unknown) => void, reject });
      this.child!.stdin.write(payload, (err) => {
        if (err) {
          this.pending.delete(id);
          reject(err);
        }
      });
    });
  }

  sendNotification(method: string, params: unknown): void {
    if (!this.child) throw new Error("rpc client not started");
    const payload = JSON.stringify({ jsonrpc: "2.0", method, params }) + "\n";
    this.child.stdin.write(payload);
  }

  private rejectAllPending(err: Error): void {
    for (const p of this.pending.values()) p.reject(err);
    this.pending.clear();
  }

  isRunning(): boolean {
    return this.child !== null && this.child.exitCode === null && !this.child.killed;
  }

  stop(): void {
    if (this.child && this.isRunning()) {
      this.child.kill();
    }
    this.child = null;
  }
}
