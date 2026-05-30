import assert from "node:assert/strict";
import test from "node:test";

import type { ApplianceUpdateStatus } from "./applianceUpdateStatus";
import { summarizeApplianceUpdateStatus } from "./applianceUpdateStatus";

const NO_SOURCE_MESSAGE =
  "Unicron updates are unavailable because this container was started from a local image. Restart the appliance with the official Docker Hub image logforge/unicron:latest to receive updates.";

function status(overrides: Partial<ApplianceUpdateStatus> = {}): ApplianceUpdateStatus {
  return {
    status: "ok",
    updater_health: "ok",
    auto_update_enabled: true,
    check_state: "ok",
    in_progress: false,
    update_available: false,
    rollback_available: false,
    ...overrides,
  };
}

test("summarizes an up-to-date check", () => {
  assert.deepEqual(summarizeApplianceUpdateStatus({ status: status() }), {
    message: "Up to date",
    tone: "success",
  });
});

test("summarizes an available update", () => {
  assert.deepEqual(summarizeApplianceUpdateStatus({ status: status({ update_available: true }) }), {
    message: "New image pulled; ready to update",
    tone: "info",
  });
});

test("summarizes a pending check action", () => {
  assert.deepEqual(summarizeApplianceUpdateStatus({ status: status(), action: "check" }), {
    message: "Checking for updates...",
    tone: "info",
  });
});

test("summarizes a pending apply action", () => {
  assert.deepEqual(summarizeApplianceUpdateStatus({ status: status({ update_available: true }), action: "apply" }), {
    message: "Pulling new image...",
    tone: "info",
  });
});

test("summarizes a missing registry update source", () => {
  assert.deepEqual(
    summarizeApplianceUpdateStatus({
      status: status({
        status: "no_update_source",
        check_state: "no_update_source",
        last_error: NO_SOURCE_MESSAGE,
      }),
    }),
    {
      message: NO_SOURCE_MESSAGE,
      tone: "warning",
    },
  );
});

test("summarizes degraded updater status", () => {
  assert.deepEqual(
    summarizeApplianceUpdateStatus({
      status: status({
        status: "degraded",
        updater_health: "unavailable",
        last_error: "Appliance updater is unavailable: connection refused",
      }),
    }),
    {
      message: "Appliance updater is unavailable: connection refused",
      tone: "warning",
    },
  );
});
