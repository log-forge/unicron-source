import assert from "node:assert/strict";
import test from "node:test";
import type { QueryClient } from "@tanstack/react-query";

import { handleRegister } from "./registerHandler";
import type { HeraldRegisterEventData } from "../../types/socket/herald.types";
import type { AgentRefusalModalData } from "../../utils/agentRefusalModal";

function memoryStorage(): Pick<Storage, "getItem" | "setItem"> {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
  };
}

function socketHarness() {
  const handlers = new Map<string, (data: HeraldRegisterEventData) => void>();
  const socket = {
    off: (event: string) => {
      handlers.delete(event);
    },
    on: (event: string, handler: (data: HeraldRegisterEventData) => void) => {
      handlers.set(event, handler);
    },
  };
  return {
    socket,
    emitRegistered: (data: HeraldRegisterEventData) => handlers.get("herald:registered")?.(data),
  };
}

function queryClientHarness() {
  const invalidations: Array<{ queryKey?: unknown[]; exact?: boolean }> = [];
  const queryClient = {
    invalidateQueries: (args: { queryKey?: unknown[]; exact?: boolean }) => {
      invalidations.push(args);
      return Promise.resolve();
    },
  } as unknown as QueryClient;
  return { queryClient, invalidations };
}

const registrationFailureEvent: HeraldRegisterEventData = {
  herald_id: "edge-remote",
  herald_name: "edge-remote",
  status: "failed",
  reason: "Bootstrap failed.",
  failure: {
    code: "REGISTER_FAILED",
    message: "Bootstrap failed.",
  },
};

test("register handler opens the refusal modal for structured failures", () => {
  const { socket, emitRegistered } = socketHarness();
  const { queryClient } = queryClientHarness();
  const opened: AgentRefusalModalData[] = [];

  handleRegister(socket as never, queryClient, {
    openAgentRefusalModal: (refusal) => opened.push(refusal),
    modalStorage: memoryStorage(),
  });

  emitRegistered(registrationFailureEvent);

  assert.equal(opened.length, 1);
  assert.equal(opened[0].herald_name, "edge-remote");
  assert.equal(opened[0].failure.code, "REGISTER_FAILED");
});

test("generic failed registration invalidates queries without structured modal", () => {
  const { socket, emitRegistered } = socketHarness();
  const { queryClient, invalidations } = queryClientHarness();
  const opened: AgentRefusalModalData[] = [];

  handleRegister(socket as never, queryClient, {
    openAgentRefusalModal: (refusal) => opened.push(refusal),
    modalStorage: memoryStorage(),
  });

  emitRegistered({
    herald_id: "edge-remote",
    herald_name: "edge-remote",
    status: "failed",
    reason: "Agent bootstrap failed",
  });

  assert.equal(opened.length, 0);
  assert.ok(invalidations.some((entry) => JSON.stringify(entry.queryKey) === JSON.stringify(["agents"])));
});

test("register handler dedupes retry-loop refusal events", () => {
  const { socket, emitRegistered } = socketHarness();
  const { queryClient } = queryClientHarness();
  const opened: AgentRefusalModalData[] = [];

  handleRegister(socket as never, queryClient, {
    openAgentRefusalModal: (refusal) => opened.push(refusal),
    modalStorage: memoryStorage(),
  });

  emitRegistered(registrationFailureEvent);
  emitRegistered(registrationFailureEvent);

  assert.equal(opened.length, 1);
});
