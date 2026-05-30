import assert from "node:assert/strict";
import test from "node:test";

import { getNotifierTheme } from "./notifier/theme";

test("creates notifier MUI themes from shared token fallbacks without a DOM", () => {
  const lightTheme = getNotifierTheme("light");
  const darkTheme = getNotifierTheme("dark");

  assert.equal(lightTheme.palette.mode, "light");
  assert.equal(lightTheme.palette.primary.main, "#5f25e6");
  assert.equal(lightTheme.palette.info.main, "#ff5800");
  assert.equal(lightTheme.palette.background.default, "#f7f7f7");
  assert.equal(lightTheme.palette.logoText, "#242424");

  assert.equal(darkTheme.palette.mode, "dark");
  assert.equal(darkTheme.palette.primary.main, "#9d79ee");
  assert.equal(darkTheme.palette.info.main, "#ff8b4d");
  assert.equal(darkTheme.palette.background.default, "#141414");
  assert.equal(darkTheme.palette.logoText, "#f7f7f7");
});

test("notifier theme no longer uses the legacy standalone palette", () => {
  const palette = JSON.stringify(getNotifierTheme("light").palette);

  assert.doesNotMatch(palette, /#2469DC|#5A8BE6|#1A4EB0|#ff9800/i);
});

test("creates notifier MUI themes when runtime CSS variables resolve to OKLCH", () => {
  const globals = globalThis as Record<string, unknown>;
  const originalWindow = globals.window;
  const originalDocument = globals.document;
  const originalGetComputedStyle = globals.getComputedStyle;
  const root = {};

  globals.window = {};
  globals.document = { documentElement: root };
  globals.getComputedStyle = () => ({
    getPropertyValue(token: string) {
      if (token.startsWith("--color-")) {
        return "oklch(0.65 0.15 145)";
      }

      return "";
    },
  });

  try {
    const theme = getNotifierTheme("light");
    assert.doesNotThrow(() => getNotifierTheme("light"));
    assert.match(theme.palette.primary.main, /^rgb\(\d+, \d+, \d+\)$/);
  } finally {
    if (originalWindow === undefined) delete globals.window;
    else globals.window = originalWindow;

    if (originalDocument === undefined) delete globals.document;
    else globals.document = originalDocument;

    if (originalGetComputedStyle === undefined) delete globals.getComputedStyle;
    else globals.getComputedStyle = originalGetComputedStyle;
  }
});
