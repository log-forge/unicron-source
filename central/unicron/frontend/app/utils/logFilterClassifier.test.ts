import assert from "node:assert/strict";
import test from "node:test";

import { classifyFilter, resolveViewerMode } from "./logFilterClassifier";

test("classifyFilter keeps plain colon text on the fast lane", () => {
  assert.equal(classifyFilter("http://service"), "fast-lane");
  assert.equal(classifyFilter("12:34:56"), "fast-lane");
  assert.equal(classifyFilter("error:timeout"), "fast-lane");
});

test("classifyFilter still recognizes known LogsQL fields", () => {
  assert.equal(classifyFilter("severity:error"), "vtail");
  assert.equal(classifyFilter("container_key:host-a:web"), "vtail");
  assert.equal(classifyFilter('severity:error | stats count()'), "vquery");
});

test("resolveViewerMode forces unmonitored containers onto fast lane", () => {
  assert.equal(resolveViewerMode("severity:error", false), "fast-lane");
  assert.equal(resolveViewerMode("severity:error | stats count()", false), "fast-lane");
  assert.equal(resolveViewerMode("severity:error", true), "vtail");
});
