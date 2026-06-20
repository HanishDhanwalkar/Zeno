/**
 * Context pruning.
 *
 * Strategy:
 *  - System messages are always kept (in place).
 *  - The most recent user message and everything after it (the active
 *    exchange) is always kept untouched.
 *  - Older assistant/tool messages are kept newest-first until the token
 *    budget is exhausted; the rest are dropped.
 *  - A leading orphan `tool` message (whose assistant tool-call got dropped)
 *    is trimmed so the surviving sequence stays API-valid.
 */

import type { Message } from "./protocol.js";
import { countMessageTokens } from "./tokens.js";

export const DEFAULT_PROTECTED_TOKENS = 40_000;

export function prune(
  messages: Message[],
  protectedTokens: number = DEFAULT_PROTECTED_TOKENS,
): Message[] {
  if (messages.length === 0) return [];

  const kept = new Set<number>();

  // Always keep system messages.
  messages.forEach((m, i) => {
    if (m.role === "system") kept.add(i);
  });

  // Find the start of the active exchange: the last user message.
  let lastUser = -1;
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === "user") {
      lastUser = i;
      break;
    }
  }
  const tailStart = lastUser === -1 ? messages.length : lastUser;
  for (let i = tailStart; i < messages.length; i++) kept.add(i);

  // Walk the head (everything before the active exchange) newest-first,
  // accumulating non-system tokens until the budget is hit.
  let used = 0;
  let cutoff = tailStart; // first head index we keep
  for (let i = tailStart - 1; i >= 0; i--) {
    if (messages[i].role === "system") continue;
    const cost = countMessageTokens([messages[i]]);
    if (used + cost > protectedTokens) break;
    used += cost;
    cutoff = i;
  }
  for (let i = cutoff; i < tailStart; i++) kept.add(i);

  // Trim a leading orphan tool message in the kept head region.
  for (let i = cutoff; i < tailStart; i++) {
    if (!kept.has(i)) continue;
    if (messages[i].role === "tool") {
      kept.delete(i);
    } else {
      break;
    }
  }

  return messages.filter((_, i) => kept.has(i));
}
