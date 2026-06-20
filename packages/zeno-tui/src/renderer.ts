/**
 * The Renderer interface — the single seam between Zeno's logic and its UI.
 *
 * Everything outside the renderer implementations talks to this interface, so
 * the Ink (React) renderer can later be swapped for a zero-dependency in-house
 * renderer without touching the session/agent code.
 */

import type { ToolResult } from "zeno-coding-agent";

export interface Renderer {
  /** Initialise the UI (clear screen, draw frame, etc.). */
  start(): void | Promise<void>;

  /** A complete, non-streamed line (e.g. the user's own input echoed back). */
  addMessage(role: "user" | "assistant" | "system", text: string): void;

  // -- streaming assistant output --
  beginAssistant(): void;
  appendAssistant(text: string): void;
  endAssistant(): void;

  // -- tool activity --
  toolCall(name: string, args: Record<string, unknown>): void;
  toolResult(name: string, result: ToolResult): void;

  error(message: string): void;

  /** Status bar: model, token count, session status. */
  setStatusLine(text: string): void;

  /** Confirm a gated action. Resolves true to allow, false to deny. */
  requestPermission(message: string): Promise<boolean>;

  /** Read the next line of user input. Resolves null on EOF / exit request. */
  prompt(): Promise<string | null>;

  /** Register a handler fired when the user requests cancellation (Ctrl+C). */
  onCancel(handler: () => void): void;

  /** Tear down the UI and release the terminal. */
  stop(): void;
}
