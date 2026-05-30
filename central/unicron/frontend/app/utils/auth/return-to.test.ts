import assert from "node:assert/strict";
import test from "node:test";

import { normalizeReturnTo } from "./return-to";

test("normalizeReturnTo strips the app basename from in-app paths", () => {
  assert.equal(normalizeReturnTo("/unicron/overview?tab=logs", "/unicron/"), "/overview?tab=logs");
  assert.equal(normalizeReturnTo("/unicron", "/unicron/"), "/");
});

test("normalizeReturnTo rejects external and auth-internal targets", () => {
  assert.equal(normalizeReturnTo("https://evil.example/overview", "/unicron/"), "/");
  assert.equal(normalizeReturnTo("/auth/callback", "/unicron/"), "/");
  assert.equal(normalizeReturnTo("/unicron/auth/callback?returnTo=%2Foverview", "/unicron/"), "/");
});
