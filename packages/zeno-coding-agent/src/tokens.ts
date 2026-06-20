/**
 * Approximate token counting, mirroring zeno_ai/tokens.py so Node and Python
 * agree closely. Rough by design; swap for a real tokenizer later.
 */

import type { Message } from "./protocol.js";

const CHARS_PER_TOKEN = 4;

export function countTokens(text: string | null | undefined): number {
  if (!text) return 0;
  const words = text.split(/\s+/).filter(Boolean).length;
  const chars = text.length;
  return Math.max(words, Math.floor(chars / CHARS_PER_TOKEN), 1);
}

function contentToText(content: Message["content"]): string {
  if (content == null) return "";
  return typeof content === "string" ? content : String(content);
}

export function countMessageTokens(messages: Message[]): number {
  let total = 0;
  for (const msg of messages) {
    total += 4; // per-message overhead
    total += countTokens(contentToText(msg.content));
    for (const call of msg.tool_calls ?? []) {
      total += countTokens(call.function?.name);
      const args = call.function?.arguments;
      total += countTokens(typeof args === "string" ? args : JSON.stringify(args));
    }
    if (msg.name) total += countTokens(msg.name);
  }
  return total;
}
