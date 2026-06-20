import test from "node:test";
import assert from "node:assert/strict";
import { prune } from "./prune.js";
import type { Message } from "./protocol.js";

test("keeps system, last user, and following messages", () => {
  const messages: Message[] = [
    { role: "system", content: "sys" },
    { role: "user", content: "old question" },
    { role: "assistant", content: "old answer" },
    { role: "user", content: "new question" },
  ];
  const out = prune(messages, 100000);
  assert.equal(out[0].role, "system");
  assert.equal(out[out.length - 1].content, "new question");
});

test("drops old messages when over budget but keeps active exchange", () => {
  const big = "x ".repeat(20000); // ~10k tokens each
  const messages: Message[] = [
    { role: "system", content: "sys" },
    { role: "user", content: "q1" },
    { role: "assistant", content: big },
    { role: "assistant", content: big },
    { role: "assistant", content: big },
    { role: "user", content: "current" },
  ];
  const out = prune(messages, 15000);
  assert.ok(out.some((m) => m.role === "system"));
  assert.equal(out[out.length - 1].content, "current");
  // Not all three big assistant messages survive a 15k budget.
  const bigKept = out.filter((m) => m.content === big).length;
  assert.ok(bigKept < 3);
});

test("trims leading orphan tool message", () => {
  const big = "x ".repeat(20000);
  const messages: Message[] = [
    { role: "assistant", content: big, tool_calls: [{ id: "a", type: "function", function: { name: "read", arguments: {} } }] },
    { role: "tool", tool_call_id: "a", name: "read", content: big },
    { role: "user", content: "current" },
  ];
  // Budget large enough only for the tool message, forcing the assistant to drop.
  const out = prune(messages, 9000);
  assert.equal(out[0].role, "user");
});

test("single message survives", () => {
  const out = prune([{ role: "user", content: "hi" }]);
  assert.equal(out.length, 1);
});

test("empty input returns empty", () => {
  assert.deepEqual(prune([]), []);
});
