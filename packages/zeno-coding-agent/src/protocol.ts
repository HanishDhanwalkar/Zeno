/**
 * Shared JSON-RPC 2.0 protocol between Node (client) and Python (server).
 *
 * Transport: NDJSON over stdio, one JSON object per line. Node spawns Python
 * and keeps it warm for the whole session.
 *
 * The Python side (zeno_agent_core) implements the matching shapes; keep both
 * in sync when changing this file.
 */

export type Role = "system" | "user" | "assistant" | "tool";

export interface ToolCall {
  id: string;
  type: "function";
  function: { name: string; arguments: unknown };
}

export interface Message {
  role: Role;
  content: string | null;
  /** assistant turns that requested tools */
  tool_calls?: ToolCall[];
  /** tool turns reference the call they answer */
  tool_call_id?: string;
  /** tool name (for tool turns) */
  name?: string;
}

/** Structured result returned by every tool. */
export interface ToolResult {
  output: string;
  truncated: boolean;
  exitCode?: number;
  error?: string;
}

// ---- Requests: Node -> Python ------------------------------------------

export interface AgentRunParams {
  streamId: string;
  messages: Message[];
  systemPrompt?: string;
  tools?: unknown[];
  model?: string;
  projectRoot?: string;
  /** ask Node for permission on each tool call (default true) */
  gatePermissions?: boolean;
}

export interface AgentRunResult {
  ok: boolean;
  reason: string;
}

// ---- Notifications: Node -> Python -------------------------------------

export interface StreamCancelParams {
  streamId: string;
}

export interface PermissionDecisionParams {
  streamId: string;
  callId: string;
  allow: boolean;
  reason?: string;
  updatedArgs?: Record<string, unknown>;
}

// ---- Notifications: Python -> Node -------------------------------------

export interface SystemReadyParams {
  providers: string[];
}

export interface TextDeltaParams {
  streamId: string;
  content: string;
}

export interface ToolCallParams {
  streamId: string;
  id: string;
  name: string;
  args: Record<string, unknown>;
}

export interface ToolResultParams {
  streamId: string;
  id: string;
  name: string;
  result: ToolResult;
}

export interface PermissionRequestParams {
  streamId: string;
  callId: string;
  name: string;
  args: Record<string, unknown>;
}

export interface StreamEndParams {
  streamId: string;
  reason: string;
}

export interface StreamErrorParams {
  streamId: string;
  message: string;
}

/** Method-name constants to avoid typos across the codebase. */
export const RPC = {
  // requests
  agentRun: "agent/run",
  // node -> python notifications
  streamCancel: "stream/cancel",
  permissionDecision: "permission/decision",
  // python -> node notifications
  systemReady: "system/ready",
  textDelta: "stream/textDelta",
  toolCall: "stream/toolCall",
  toolResult: "stream/toolResult",
  permissionRequest: "stream/permissionRequest",
  streamEnd: "stream/end",
  streamError: "stream/error",
} as const;
