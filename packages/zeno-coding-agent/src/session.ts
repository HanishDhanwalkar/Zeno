/**
 * Session manager: canonical conversation state + the bridge between the TUI
 * and the Python agent-core.
 *
 * Responsibilities:
 *  - Keep the canonical `Message[]` history.
 *  - On each user message: append, prune, dispatch `agent/run`.
 *  - Forward stream notifications to renderer callbacks.
 *  - Reconstruct assistant/tool turns into history (Python is stateless).
 *  - Run the permission gate, prompting the user only when needed.
 */

import { randomUUID } from "node:crypto";
import type { RpcClient } from "./rpcClient.js";
import { classify } from "./permission.js";
import { prune, DEFAULT_PROTECTED_TOKENS } from "./prune.js";
import { countMessageTokens } from "./tokens.js";
import {
  RPC,
  type Message,
  type PermissionRequestParams,
  type StreamEndParams,
  type StreamErrorParams,
  type TextDeltaParams,
  type ToolCallParams,
  type ToolResultParams,
  type ToolCall,
  type ToolResult,
} from "./protocol.js";

export interface PermissionPrompt {
  name: string;
  args: Record<string, unknown>;
  reason: string;
}

export interface SessionCallbacks {
  onTextDelta?(content: string): void;
  onToolCall?(p: ToolCallParams): void;
  onToolResult?(p: ToolResultParams): void;
  onError?(message: string): void;
  onStreamEnd?(reason: string): void;
  onStatus?(text: string): void;
  /** Return true to allow, false to deny. */
  onPermissionPrompt?(prompt: PermissionPrompt): Promise<boolean>;
}

export interface SessionOptions {
  client: RpcClient;
  projectRoot: string;
  model?: string;
  systemPrompt?: string;
  protectedTokens?: number;
  callbacks?: SessionCallbacks;
}

function formatToolResult(result: ToolResult): string {
  if (result.error) return `ERROR: ${result.error}`;
  let out = result.output ?? "";
  if (result.truncated) out += "\n[... output truncated ...]";
  return out;
}

export class SessionManager {
  readonly sessionId = randomUUID();
  readonly projectRoot: string;
  model: string;
  readonly systemPrompt: string;
  readonly protectedTokens: number;
  messages: Message[] = [];

  private client: RpcClient;
  private cb: SessionCallbacks;
  private activeStreamId: string | null = null;
  private listenerBound = false;

  constructor(opts: SessionOptions) {
    this.client = opts.client;
    this.projectRoot = opts.projectRoot;
    this.model = opts.model ?? "mock";
    this.systemPrompt = opts.systemPrompt ?? "";
    this.protectedTokens = opts.protectedTokens ?? DEFAULT_PROTECTED_TOKENS;
    this.cb = opts.callbacks ?? {};
    if (this.systemPrompt) {
      this.messages.push({ role: "system", content: this.systemPrompt });
    }
  }

  get tokenCount(): number {
    return countMessageTokens(this.messages);
  }

  /** Send a user turn and resolve when the stream ends. */
  sendUserMessage(text: string): Promise<string> {
    this.messages.push({ role: "user", content: text });
    const pruned = prune(this.messages, this.protectedTokens);
    const streamId = randomUUID();
    this.activeStreamId = streamId;

    // Per-run turn reconstruction state.
    let bufText = "";
    let bufCalls: ToolCall[] = [];
    let phase: "collect" | "results" = "collect";

    const flushAssistant = () => {
      if (bufText || bufCalls.length) {
        const msg: Message = { role: "assistant", content: bufText || null };
        if (bufCalls.length) msg.tool_calls = bufCalls;
        this.messages.push(msg);
      }
      bufText = "";
      bufCalls = [];
    };

    return new Promise<string>((resolve) => {
      const onNotification = (method: string, params: any) => {
        if (params?.streamId && params.streamId !== streamId) return;

        switch (method) {
          case RPC.textDelta: {
            if (phase === "results") phase = "collect";
            bufText += (params as TextDeltaParams).content;
            this.cb.onTextDelta?.((params as TextDeltaParams).content);
            break;
          }
          case RPC.toolCall: {
            if (phase === "results") phase = "collect";
            const p = params as ToolCallParams;
            bufCalls.push({
              id: p.id,
              type: "function",
              function: { name: p.name, arguments: p.args },
            });
            this.cb.onToolCall?.(p);
            break;
          }
          case RPC.toolResult: {
            const p = params as ToolResultParams;
            if (phase === "collect") {
              flushAssistant();
              phase = "results";
            }
            this.messages.push({
              role: "tool",
              tool_call_id: p.id,
              name: p.name,
              content: formatToolResult(p.result),
            });
            this.cb.onToolResult?.(p);
            break;
          }
          case RPC.permissionRequest: {
            void this.handlePermission(streamId, params as PermissionRequestParams);
            break;
          }
          case RPC.streamError: {
            this.cb.onError?.((params as StreamErrorParams).message);
            break;
          }
          case RPC.streamEnd: {
            if (phase === "collect") flushAssistant();
            this.client.off("notification", onNotification);
            this.activeStreamId = null;
            const reason = (params as StreamEndParams).reason;
            this.cb.onStreamEnd?.(reason);
            resolve(reason);
            break;
          }
        }
      };

      this.client.on("notification", onNotification);
      this.client
        .sendRequest(RPC.agentRun, {
          streamId,
          messages: pruned,
          systemPrompt: this.systemPrompt,
          model: this.model,
          projectRoot: this.projectRoot,
          gatePermissions: true,
        })
        .catch((err) => {
          this.client.off("notification", onNotification);
          this.cb.onError?.(String(err?.message ?? err));
          this.activeStreamId = null;
          resolve("error");
        });
    });
  }

  private async handlePermission(
    streamId: string,
    req: PermissionRequestParams,
  ): Promise<void> {
    const c = classify(req.name, req.args, this.projectRoot);
    let allow: boolean;
    let reason = c.reason;

    if (c.verdict === "allow") {
      allow = true;
    } else if (c.verdict === "deny") {
      allow = false;
    } else if (this.cb.onPermissionPrompt) {
      allow = await this.cb.onPermissionPrompt({
        name: req.name,
        args: req.args,
        reason: c.reason,
      });
      reason = allow ? "approved by user" : "denied by user";
    } else {
      allow = false;
      reason = `blocked (${c.reason}); no prompt handler`;
    }

    this.client.sendNotification(RPC.permissionDecision, {
      streamId,
      callId: req.callId,
      allow,
      reason,
    });
  }

  cancel(): void {
    if (this.activeStreamId) {
      this.client.sendNotification(RPC.streamCancel, { streamId: this.activeStreamId });
    }
  }
}
