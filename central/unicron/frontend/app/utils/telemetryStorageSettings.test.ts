import assert from "node:assert/strict";
import test from "node:test";

import { buildTelemetryStorageSettings } from "./telemetryStorageSettings";

test("source-available telemetry storage shows seven-day retention and no configured size caps", () => {
  const settings = buildTelemetryStorageSettings();

  assert.deepEqual(settings.retention, [
    { key: "metrics", label: "Metrics retention", value: "7 days" },
    { key: "logs", label: "Logs retention", value: "7 days" },
  ]);
  assert.equal(settings.canSave, false);
  assert.equal(settings.storageLimits.length, 2);
  for (const control of settings.storageLimits) {
    assert.equal(control.disabled, true);
    assert.equal(control.value, "No cap");
  }
});
