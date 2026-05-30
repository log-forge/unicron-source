import assert from "node:assert/strict";
import test from "node:test";

import {
  getChartSeriesColor,
  getChartSurfaceColors,
  getSeverityBadgeClasses,
  getSeverityTone,
  getStatusBadgeClasses,
  getStatusTone,
  getToneBadgeClasses,
  getToneDotClasses,
  getToneIconClasses,
  getToneSoftSurfaceClasses,
  readThemeColor,
  themeColorVar,
  type ThemeTone,
} from "./index";

const rawPalettePattern = /\b(red|amber|yellow|green|emerald|blue|slate|gray|purple)\b|#[0-9a-f]{3,8}/i;

test("maps severity vocabulary to shared theme tones", () => {
  assert.equal(getSeverityTone("critical"), "error");
  assert.equal(getSeverityTone("warning"), "warning");
  assert.equal(getSeverityTone("info"), "info");
  assert.equal(getSeverityTone(" CRITICAL "), "error");
  assert.equal(getSeverityTone("notice"), "neutral");
  assert.equal(getSeverityTone(), "neutral");
});

test("maps success-like status vocabulary to success", () => {
  for (const status of ["healthy", "ok", "running", "sent", "allowed", "success"]) {
    assert.equal(getStatusTone(status), "success");
  }
});

test("maps warning-like status vocabulary to warning", () => {
  for (const status of ["warning", "degraded", "pending", "retrying", "starting", "restarting", "paused", "acknowledged"]) {
    assert.equal(getStatusTone(status), "warning");
  }
});

test("maps error-like status vocabulary to error", () => {
  for (const status of ["critical", "error", "failed", "unhealthy", "firing", "triggered", "blocked", "stopped", "exited"]) {
    assert.equal(getStatusTone(status), "error");
  }
});

test("maps neutral-like and unsupported status vocabulary to neutral", () => {
  for (const status of ["unknown", "disabled", "silenced", "resolved", "created", "group", "", "unsupported"]) {
    assert.equal(getStatusTone(status), "neutral");
  }
});

test("normalizes mixed-case and padded status inputs", () => {
  assert.equal(getStatusTone(" RetryIng "), "warning");
  assert.equal(getStatusTone(" SENT "), "success");
  assert.equal(getStatusTone(" ExItEd "), "error");
});

test("returns semantic token classes for dynamic status rendering", () => {
  const tones: ThemeTone[] = ["success", "warning", "error", "neutral", "info"];
  const classes = tones.flatMap((tone) => [
    getToneBadgeClasses(tone),
    getToneDotClasses(tone),
    getToneIconClasses(tone),
    getToneSoftSurfaceClasses(tone),
  ]);

  classes.push(getSeverityBadgeClasses("critical"));
  classes.push(getSeverityBadgeClasses("info"));
  classes.push(getStatusBadgeClasses("retrying"));
  classes.push(getStatusBadgeClasses("sent"));

  for (const className of classes) {
    assert.doesNotMatch(className, rawPalettePattern);
    assert.match(className, /(success|warning|error|neutral|info)/);
  }
});

test("returns shared CSS variable references for non-Tailwind consumers", () => {
  assert.equal(themeColorVar("warning"), "var(--color-warning)");
  assert.equal(themeColorVar("color-warning"), "var(--color-warning)");
  assert.equal(themeColorVar("--color-warning"), "var(--color-warning)");
  assert.equal(readThemeColor("warning", "fallback"), "fallback");

  const chartColor = getChartSeriesColor("rule-123");
  assert.match(chartColor, /^var\(--color-chart-(?:[1-9]|1[0-2])\)$/);

  assert.deepEqual(getChartSurfaceColors(), {
    muted: "var(--color-chart-muted)",
    grid: "var(--color-chart-grid)",
    tooltipBackground: "var(--color-chart-tooltip-background)",
    tooltipText: "var(--color-chart-tooltip-text)",
  });
});
