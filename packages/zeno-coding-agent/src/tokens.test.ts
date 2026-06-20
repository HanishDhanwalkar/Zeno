import test from "node:test";
import assert from "node:assert/strict";
import { countTokens, countMessageTokens } from "./tokens.js";

test("empty is zero", () => {
  assert.equal(countTokens(""), 0);
  assert.equal(countTokens(null), 0);
});

test("longer text yields more tokens", () => {
  assert.ok(countTokens("a b c d e f") > countTokens("a b"));
});

test("message tokens include overhead", () => {
  const t = countMessageTokens([{ role: "user", content: "hello world" }]);
  assert.ok(t > countTokens("hello world"));
});

test("counts tool call args", () => {
  const t = countMessageTokens([
    {
      role: "assistant",
      content: null,
      tool_calls: [
        { id: "1", type: "function", function: { name: "read", arguments: { path: "a.txt" } } },
      ],
    },
  ]);
  assert.ok(t > 4);
});
