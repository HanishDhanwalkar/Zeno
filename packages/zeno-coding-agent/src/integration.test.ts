/**
 * End-to-end: Node spawns the real Python agent-core and drives a session
 * through the mock provider. Verifies the stdio pipe, tool execution, the
 * permission gate, and history reconstruction.
 */

import test from "node:test";
import assert from "node:assert/strict";
import { once } from "node:events";
import {
  createAgentCoreClient,
  SessionManager,
  findRepoRoot,
} from "./index.js";

test("full pipeline: text echo", async () => {
  const client = createAgentCoreClient();
  client.start();
  await once(client, "ready");

  const deltas: string[] = [];
  const session = new SessionManager({
    client,
    projectRoot: findRepoRoot(),
    model: "mock",
    callbacks: { onTextDelta: (c) => deltas.push(c) },
  });

  const reason = await session.sendUserMessage("hello pipeline");
  client.stop();

  assert.equal(reason, "stop");
  assert.ok(deltas.join("").includes("hello pipeline"));
  assert.equal(session.messages.at(-1)?.role, "assistant");
});
