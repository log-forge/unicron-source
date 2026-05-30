import assert from "node:assert/strict";
import test from "node:test";

import { getThemeColorPalette } from "./theme";

test("returns shared token fallbacks for non-browser theme palette consumers", () => {
  const lightPalette = getThemeColorPalette("light");
  const darkPalette = getThemeColorPalette("dark");

  assert.equal(lightPalette.background.default, "#f7f7f7");
  assert.equal(lightPalette.primary.main, "#5f25e6");
  assert.equal(lightPalette.info.main, "#ff5800");
  assert.equal(darkPalette.background.default, "#141414");
  assert.equal(darkPalette.primary.main, "#9d79ee");
  assert.equal(darkPalette.info.main, "#ff8b4d");
});
