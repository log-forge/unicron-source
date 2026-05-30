import test from "node:test";
import assert from "node:assert/strict";

import { deriveDefaultCentralUrl, normalizeCentralUrlInput } from "./agentEnrollmentCentralUrl";

test("agent enrollment defaults loopback localhost to LAN Central hostname with current UI port", () => {
  assert.equal(
    deriveDefaultCentralUrl({
      hostname: "localhost",
      origin: "https://localhost:8444",
      port: "8444",
    }),
    "https://unicron.central:8444/unicron",
  );
});

test("agent enrollment defaults loopback IPv4 to LAN Central hostname with current UI port", () => {
  assert.equal(
    deriveDefaultCentralUrl({
      hostname: "127.0.0.1",
      origin: "https://127.0.0.1:8444",
      port: "8444",
    }),
    "https://unicron.central:8444/unicron",
  );
});

test("agent enrollment defaults loopback IPv6 to LAN Central hostname with current UI port", () => {
  assert.equal(
    deriveDefaultCentralUrl({
      hostname: "[::1]",
      origin: "https://[::1]:8444",
      port: "8444",
    }),
    "https://unicron.central:8444/unicron",
  );
});

test("agent enrollment keeps real Central origin", () => {
  assert.equal(
    deriveDefaultCentralUrl({
      hostname: "central.example.com",
      origin: "https://central.example.com",
      port: "",
    }),
    "https://central.example.com/unicron",
  );
});

test("agent enrollment URL normalization preserves origin and strips trailing slash", () => {
  assert.equal(
    normalizeCentralUrlInput("central.example.com/unicron/"),
    "https://central.example.com/unicron",
  );
});
