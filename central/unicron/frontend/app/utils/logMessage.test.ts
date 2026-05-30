import test from "node:test";
import assert from "node:assert/strict";

import {
  convertLivePayloadToLog,
  convertVictoriaRowToLog,
  normalizeLogMessage,
} from "./logMessage";

test("normalizeLogMessage unwraps embedded docker json envelopes", () => {
  assert.equal(
    normalizeLogMessage(
      '{"log":"synthetic log line Lorum Ipsum\\n","stream":"stdout","time":"2026-03-24T06:07:40.308248751Z"}'
    ),
    "synthetic log line Lorum Ipsum"
  );
});

test("convertLivePayloadToLog uses the normalized message for live rows", () => {
  const log = convertLivePayloadToLog(
    '{"log":"synthetic log line Lorum Ipsum\\n","stream":"stdout","time":"2026-03-24T06:07:40.308248751Z"}',
    "2026-03-24T06:07:40.308248751Z",
    {
      stream: "stdout",
      container_key: "herald:telemetry-logger",
    }
  );
  assert.ok(log);
  assert.equal(log.message, "synthetic log line Lorum Ipsum");
});

test("convertVictoriaRowToLog prefers the unwrapped inner log text", () => {
  const log = convertVictoriaRowToLog({
    msg: '{"log":"synthetic log line Lorum Ipsum\\n","stream":"stdout","time":"2026-03-24T06:07:40.308248751Z"}',
    msg_json: {
      log: "synthetic log line Lorum Ipsum",
      stream: "stdout",
      time: "2026-03-24T06:07:40.308248751Z",
    },
    time: "2026-03-24T06:07:40.308248751Z",
  });
  assert.equal(log.message, "synthetic log line Lorum Ipsum");
});

test("convertVictoriaRowToLog falls back to Victoria alias fields for history rows", () => {
  const log = convertVictoriaRowToLog({
    _time: "2026-04-02T05:47:10.398284Z",
    _msg: "rule worker heartbeat",
    container_key: "local:unicron-demo-rule-worker",
  });

  assert.equal(log.timeStamp, "2026-04-02T05:47:10.398284Z");
  assert.equal(log.message, "rule worker heartbeat");
});
