import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAgentDeregisterPath,
  buildAgentRemovalConfirmation,
  getAgentRemovalLabel,
  removeAgentFromRows,
} from "./agentRemoval";

test("blocked agents use remove copy and require a fresh enrollment", () => {
  const copy = buildAgentRemovalConfirmation("edge-a", "blocked");

  assert.equal(getAgentRemovalLabel("blocked"), "Remove");
  assert.match(copy, /Remove refused agent "edge-a"/);
  assert.match(copy, /invalidates its enrollment identity/);
  assert.match(copy, /Enroll the host again/);
});

test("registered agents keep decommission copy", () => {
  const copy = buildAgentRemovalConfirmation("edge-a", "offline");

  assert.equal(getAgentRemovalLabel("offline"), "Decommission");
  assert.match(copy, /decommission agent "edge-a"/);
  assert.match(copy, /disconnect the agent immediately/);
});

test("deregister path encodes agent id for the shared delete endpoint", () => {
  assert.equal(buildAgentDeregisterPath("edge/a"), "/agent/edge%2Fa/deregister");
});

test("removed agent rows are filtered by id and displayed name", () => {
  const rows = [
    { agent_id: "edge-a", agent_name: "edge-a" },
    { agent_id: "token-random-id", agent_name: "edge-b" },
    { agent_id: "edge-c", agent_name: "edge-c" },
  ];

  assert.deepEqual(removeAgentFromRows(rows, "token-random-id", "edge-b"), [
    { agent_id: "edge-a", agent_name: "edge-a" },
    { agent_id: "edge-c", agent_name: "edge-c" },
  ]);
});
