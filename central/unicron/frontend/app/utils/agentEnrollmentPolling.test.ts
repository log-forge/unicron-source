import assert from "node:assert/strict";
import test from "node:test";

import {
  ENROLLMENT_POLL_MAX_SECONDS,
  getEnrollmentPollingCutoffMs,
  shouldStopEnrollmentPolling,
  type PendingEnrollment,
} from "./agentEnrollmentPolling";

const pending: PendingEnrollment = {
  agentName: "edge-a",
  issuedAt: 1000,
  expiresAt: 1300,
};

test("enrollment polling cuts off after sixty seconds when token lives longer", () => {
  assert.equal(getEnrollmentPollingCutoffMs(pending), (pending.issuedAt + ENROLLMENT_POLL_MAX_SECONDS) * 1000);
  assert.equal(shouldStopEnrollmentPolling(pending, [], (pending.issuedAt + 59) * 1000, true), false);
  assert.equal(shouldStopEnrollmentPolling(pending, [], (pending.issuedAt + 60) * 1000, true), true);
});

test("enrollment polling cuts off at token expiry when earlier than sixty seconds", () => {
  const shortLived = { ...pending, expiresAt: pending.issuedAt + 12 };

  assert.equal(getEnrollmentPollingCutoffMs(shortLived), shortLived.expiresAt * 1000);
  assert.equal(shouldStopEnrollmentPolling(shortLived, [], (shortLived.expiresAt - 1) * 1000, true), false);
  assert.equal(shouldStopEnrollmentPolling(shortLived, [], shortLived.expiresAt * 1000, true), true);
});

test("enrollment polling stops when matching agent reaches a terminal row status", () => {
  assert.equal(
    shouldStopEnrollmentPolling(
      pending,
      [{ agent_id: "agent-1", agent_name: "edge-a", status: "blocked" }],
      (pending.issuedAt + 5) * 1000,
      true,
    ),
    true,
  );
  assert.equal(
    shouldStopEnrollmentPolling(
      pending,
      [{ agent_id: "edge-a", agent_name: "edge-a", status: "online" }],
      (pending.issuedAt + 5) * 1000,
      true,
    ),
    true,
  );
  assert.equal(
    shouldStopEnrollmentPolling(
      pending,
      [{ agent_id: "other", agent_name: "other", status: "blocked" }],
      (pending.issuedAt + 5) * 1000,
      true,
    ),
    false,
  );
});

test("enrollment polling stops when the enrollment dialog closes", () => {
  assert.equal(shouldStopEnrollmentPolling(pending, [], (pending.issuedAt + 5) * 1000, false), true);
});
