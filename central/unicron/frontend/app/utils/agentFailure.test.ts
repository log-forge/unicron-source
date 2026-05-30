import assert from "node:assert/strict";
import test from "node:test";

import { buildAgentFailureDisplay, getAgentStatusLabel } from "./agentFailure";

test("formats agent refusal copy", () => {
  const display = buildAgentFailureDisplay("blocked", {
    code: "REGISTER_FAILED",
    message: "Agent registration failed.",
  });

  assert.equal(display.statusLabel, "Refused");
  assert.equal(display.message, "Agent registration failed.");
  assert.equal(display.detail, undefined);
  assert.equal(display.compactDetail, "REGISTER_FAILED");
});

test("maps agent statuses", () => {
  assert.equal(getAgentStatusLabel("blocked"), "Refused");
  assert.equal(buildAgentFailureDisplay("blocked", null).compactDetail, "Registration refused");
  assert.equal(buildAgentFailureDisplay("online", null).statusLabel, "Online");
  assert.equal(buildAgentFailureDisplay("offline", null).statusLabel, "Offline");
});
