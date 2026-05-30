import assert from "node:assert/strict";
import test from "node:test";

import { removeHostFromContainersCache } from "./containerRealtimeCache";

test("removed host-status events drop the host and its containers from overview cache", () => {
  const next = removeHostFromContainersCache(
    {
      hosts: [
        { host_id: "local", online: true },
        { host_id: "edge-a", online: true },
      ],
      containers: [
        { container_key: "local:web", host_id: "local" },
        { container_key: "edge-a:api", host_id: "edge-a" },
        { container_key: "edge-a:worker", host_id: "edge-a" },
      ],
      groups: [],
    },
    "edge-a",
  );

  assert.deepEqual(next?.hosts.map((host) => host.host_id), ["local"]);
  assert.deepEqual(next?.containers.map((container) => container.container_key), ["local:web"]);
  assert.deepEqual(next?.groups, []);
});
