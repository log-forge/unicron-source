import assert from "node:assert/strict";
import test from "node:test";

import {
  buildAgentRefusalModalKey,
  clearAgentRefusalModalClaims,
  openAgentRefusalModalOnce,
  openFirstBlockedAgentRefusalOnce,
  type AgentRefusalModalData,
} from "./agentRefusalModal";

function memoryStorage(): Pick<Storage, "getItem" | "key" | "length" | "removeItem" | "setItem"> {
  const values = new Map<string, string>();
  return {
    get length() {
      return values.size;
    },
    getItem: (key: string) => values.get(key) ?? null,
    key: (index: number) => Array.from(values.keys())[index] ?? null,
    removeItem: (key: string) => {
      values.delete(key);
    },
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
}

const refusal: AgentRefusalModalData = {
  herald_id: "edge-a",
  herald_name: "edge-a",
  reason: "Bootstrap failed.",
  failure: {
    code: "REGISTER_FAILED",
    message: "Bootstrap failed.",
  },
};

test("builds the browser-session dedupe key from name and code", () => {
  assert.equal(
    buildAgentRefusalModalKey(refusal),
    "agent-refused:edge-a:REGISTER_FAILED",
  );
});

test("opens one refusal modal per browser session key", () => {
  const storage = memoryStorage();
  const opened: AgentRefusalModalData[] = [];

  assert.equal(openAgentRefusalModalOnce(refusal, (item) => opened.push(item), storage), true);
  assert.equal(openAgentRefusalModalOnce(refusal, (item) => opened.push(item), storage), false);

  assert.equal(opened.length, 1);
  assert.equal(opened[0].herald_name, "edge-a");
});

test("clearing an agent refusal claim allows a later same-name refusal to open", () => {
  const storage = memoryStorage();
  const opened: AgentRefusalModalData[] = [];

  assert.equal(openAgentRefusalModalOnce(refusal, (item) => opened.push(item), storage), true);
  assert.equal(openAgentRefusalModalOnce(refusal, (item) => opened.push(item), storage), false);

  assert.equal(clearAgentRefusalModalClaims("edge-a", storage), 1);
  assert.equal(openAgentRefusalModalOnce(refusal, (item) => opened.push(item), storage), true);

  assert.equal(opened.length, 2);
});

test("settings fallback opens for a blocked refusal row", () => {
  const storage = memoryStorage();
  const opened: AgentRefusalModalData[] = [];

  const didOpen = openFirstBlockedAgentRefusalOnce(
    [
      {
        agent_id: "edge-a",
        agent_name: "edge-a",
        status: "blocked",
        failure: refusal.failure,
      },
    ],
    (item) => opened.push(item),
    storage,
  );

  assert.equal(didOpen, true);
  assert.equal(opened.length, 1);
  assert.equal(opened[0].herald_name, "edge-a");
});

test("settings fallback dedupes repeated blocked refusal rows", () => {
  const storage = memoryStorage();
  const opened: AgentRefusalModalData[] = [];
  const agents = [
    {
      agent_id: "edge-a",
      agent_name: "edge-a",
      status: "blocked",
      failure: refusal.failure,
    },
  ];

  assert.equal(openFirstBlockedAgentRefusalOnce(agents, (item) => opened.push(item), storage), true);
  assert.equal(openFirstBlockedAgentRefusalOnce(agents, (item) => opened.push(item), storage), false);
  assert.equal(opened.length, 1);
});

test("settings fallback ignores blocked rows without failure details", () => {
  const opened: AgentRefusalModalData[] = [];

  const didOpen = openFirstBlockedAgentRefusalOnce(
    [
      {
        agent_id: "edge-a",
        agent_name: "edge-a",
        status: "blocked",
        failure: null,
      },
    ],
    (item) => opened.push(item),
    memoryStorage(),
  );

  assert.equal(didOpen, false);
  assert.equal(opened.length, 0);
});
