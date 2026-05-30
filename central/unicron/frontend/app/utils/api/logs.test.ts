import assert from "node:assert/strict";
import test from "node:test";

import { httpApp } from "../http.client";
import {
  getContainerFilteredLogs,
  getContainerHistoricalLogs,
  getContainerHistoricalLogsRaw,
} from "./logs";

type PostCall = {
  url: string;
  payload: Record<string, unknown>;
};

function mockHttpPost(rows: unknown[] = []) {
  const calls: PostCall[] = [];
  const originalPost = httpApp.post.bind(httpApp);

  httpApp.post = (async (url: string, payload: Record<string, unknown>) => {
    calls.push({ url, payload });
    return {
      status: 200,
      data: {
        rows,
        count: rows.length,
        query: "container_key:\"local:unicron-demo-rule-worker\"",
      },
    };
  }) as typeof httpApp.post;

  return {
    calls,
    restore() {
      httpApp.post = originalPost;
    },
  };
}

test("getContainerHistoricalLogs posts to the telemetry Victoria logs endpoint", async () => {
  const mock = mockHttpPost();

  try {
    await getContainerHistoricalLogs("local:unicron-demo-rule-worker", 60);
    assert.equal(mock.calls.length, 1);
    assert.equal(mock.calls[0]?.url, "/telemetry/victoria/logs/query");
    assert.equal(mock.calls[0]?.payload.container_key, "local:unicron-demo-rule-worker");
  } finally {
    mock.restore();
  }
});

test("getContainerFilteredLogs posts filtered history to the telemetry Victoria logs endpoint", async () => {
  const mock = mockHttpPost();

  try {
    await getContainerFilteredLogs(
      "local:unicron-demo-rule-worker",
      60,
      "msg:\"heartbeat\"",
      "| limit 50"
    );
    assert.equal(mock.calls.length, 1);
    assert.equal(mock.calls[0]?.url, "/telemetry/victoria/logs/query");
    assert.equal(mock.calls[0]?.payload.where, "msg:\"heartbeat\"");
    assert.equal(mock.calls[0]?.payload.pipes, "| limit 50");
  } finally {
    mock.restore();
  }
});

test("getContainerHistoricalLogsRaw posts to the telemetry Victoria logs endpoint", async () => {
  const mock = mockHttpPost();

  try {
    await getContainerHistoricalLogsRaw("local:unicron-demo-rule-worker", 15);
    assert.equal(mock.calls.length, 1);
    assert.equal(mock.calls[0]?.url, "/telemetry/victoria/logs/query");
  } finally {
    mock.restore();
  }
});
