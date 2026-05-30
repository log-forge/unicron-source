import test from "node:test";
import assert from "node:assert/strict";

import {
  buildOriginPolicyDisplay,
  filterEditableOrigins,
  parseOriginDraft,
  type OriginPolicy,
} from "./originPolicy";

function policy(overrides: Partial<OriginPolicy> = {}): OriginPolicy {
  return {
    effective_allowed_origins: [],
    stored_allowed_origins: [],
    protected_allowed_origins: [],
    origin_policy_source: "default",
    origin_policy_managed_by_env: false,
    origin_policy_ui_editable: true,
    origin_policy_same_origin_only: true,
    ...overrides,
  };
}

test("origin policy display treats current UI origin as required in default mode", () => {
  const display = buildOriginPolicyDisplay(policy(), "https://localhost:8444");

  assert.deepEqual(display.requiredOrigins, ["https://localhost:8444"]);
  assert.deepEqual(display.additionalOrigins, []);
  assert.deepEqual(display.allowedOrigins, ["https://localhost:8444"]);
});

test("origin policy display keeps env and current origins out of editable additions", () => {
  const display = buildOriginPolicyDisplay(
    policy({
      effective_allowed_origins: [
        "https://seed.example.com",
        "https://extra.example.com",
        "https://localhost:8444",
      ],
      stored_allowed_origins: ["https://seed.example.com", "https://extra.example.com", "https://localhost:8444"],
      protected_allowed_origins: ["https://seed.example.com"],
      origin_policy_source: "env+db",
      origin_policy_same_origin_only: false,
    }),
    "https://localhost:8444",
  );

  assert.deepEqual(display.requiredOrigins, ["https://seed.example.com", "https://localhost:8444"]);
  assert.deepEqual(display.additionalOrigins, ["https://extra.example.com"]);
  assert.deepEqual(display.allowedOrigins, [
    "https://seed.example.com",
    "https://localhost:8444",
    "https://extra.example.com",
  ]);
});

test("origin policy save payload excludes required origins from the draft", () => {
  const draft = parseOriginDraft(`
    https://seed.example.com
    https://extra.example.com, https://localhost:8444
  `);
  const editable = filterEditableOrigins(draft, ["https://seed.example.com", "https://localhost:8444"]);

  assert.deepEqual(editable, ["https://extra.example.com"]);
});
