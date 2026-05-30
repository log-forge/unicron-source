const CHART_SERIES_COUNT = 12;

export type ThemeMode = "light" | "dark";

export type ChartSurfaceColors = {
  muted: string;
  grid: string;
  tooltipBackground: string;
  tooltipText: string;
};

type ThemePaletteColor = {
  main: string;
  light: string;
  dark: string;
  contrastText: string;
};

export type ThemeColorPalette = {
  primary: ThemePaletteColor;
  secondary: ThemePaletteColor;
  success: ThemePaletteColor;
  warning: ThemePaletteColor;
  error: ThemePaletteColor;
  info: ThemePaletteColor;
  background: {
    default: string;
    paper: string;
    card: string;
    header: string;
    tab: string;
    tabHover: string;
    input: string;
    muted: string;
  };
  text: {
    primary: string;
    secondary: string;
    disabled: string;
  };
  divider: string;
  logoBackground: string;
  logoText: string;
};

const THEME_COLOR_FALLBACKS: Record<ThemeMode, ThemeColorPalette> = {
  light: {
    primary: {
      main: "#5f25e6",
      light: "#9d79ee",
      dark: "#431aa8",
      contrastText: "#ffffff",
    },
    secondary: {
      main: "#c3b9db",
      light: "#dad4e9",
      dark: "#82779d",
      contrastText: "#141414",
    },
    success: {
      main: "#3e9d55",
      light: "#71c084",
      dark: "#277039",
      contrastText: "#ffffff",
    },
    warning: {
      main: "#969100",
      light: "#c6bf1b",
      dark: "#625f00",
      contrastText: "#141414",
    },
    error: {
      main: "#c85f42",
      light: "#e38d77",
      dark: "#873a29",
      contrastText: "#ffffff",
    },
    info: {
      main: "#ff5800",
      light: "#ff8b4d",
      dark: "#a63600",
      contrastText: "#141414",
    },
    background: {
      default: "#f7f7f7",
      paper: "#e4e4e4",
      card: "#e4e4e4",
      header: "#e4e4e4",
      tab: "#f7f7f7",
      tabHover: "#d1d1d2",
      input: "#f7f7f7",
      muted: "#e4e4e4",
    },
    text: {
      primary: "#242424",
      secondary: "#8b8a8d",
      disabled: "#b7b7b8",
    },
    divider: "#d1d1d2",
    logoBackground: "#e4e4e4",
    logoText: "#242424",
  },
  dark: {
    primary: {
      main: "#9d79ee",
      light: "#bda3f3",
      dark: "#5f25e6",
      contrastText: "#141414",
    },
    secondary: {
      main: "#c3b9db",
      light: "#dad4e9",
      dark: "#5a526f",
      contrastText: "#141414",
    },
    success: {
      main: "#71c084",
      light: "#92d2a0",
      dark: "#3e9d55",
      contrastText: "#141414",
    },
    warning: {
      main: "#c6bf1b",
      light: "#d9d45f",
      dark: "#969100",
      contrastText: "#141414",
    },
    error: {
      main: "#e38d77",
      light: "#edae9f",
      dark: "#c85f42",
      contrastText: "#141414",
    },
    info: {
      main: "#ff8b4d",
      light: "#ffa978",
      dark: "#ff5800",
      contrastText: "#141414",
    },
    background: {
      default: "#141414",
      paper: "#242424",
      card: "#242424",
      header: "#242424",
      tab: "#242424",
      tabHover: "#373638",
      input: "#242424",
      muted: "#242424",
    },
    text: {
      primary: "#f7f7f7",
      secondary: "#8b8a8d",
      disabled: "#69686a",
    },
    divider: "#373638",
    logoBackground: "#373638",
    logoText: "#f7f7f7",
  },
};

function normalizeColorToken(token: string): string {
  const trimmed = token.trim();

  if (trimmed.startsWith("--")) {
    return trimmed;
  }

  if (trimmed.startsWith("color-")) {
    return `--${trimmed}`;
  }

  return `--color-${trimmed}`;
}

function clampColorChannel(value: number): number {
  return Math.min(255, Math.max(0, Math.round(value)));
}

function linearToSrgb(value: number): number {
  const clamped = Math.min(1, Math.max(0, value));
  return clamped <= 0.0031308 ? clamped * 12.92 : 1.055 * Math.pow(clamped, 1 / 2.4) - 0.055;
}

function formatRgbChannel(value: number): number {
  return clampColorChannel(linearToSrgb(value) * 255);
}

function oklchToRgb(color: string): string | undefined {
  const match = /^oklch\(\s*([+-]?(?:\d+|\d*\.\d+)%?)\s+([+-]?(?:\d+|\d*\.\d+))\s+([+-]?(?:\d+|\d*\.\d+)(?:deg)?)\s*(?:\/\s*([+-]?(?:\d+|\d*\.\d+)%?))?\s*\)$/i.exec(
    color.trim(),
  );

  if (!match) {
    return undefined;
  }

  const lightness = match[1].endsWith("%") ? Number.parseFloat(match[1]) / 100 : Number.parseFloat(match[1]);
  const chroma = Number.parseFloat(match[2]);
  const hue = Number.parseFloat(match[3]);
  const alpha = match[4]
    ? match[4].endsWith("%")
      ? Number.parseFloat(match[4]) / 100
      : Number.parseFloat(match[4])
    : undefined;

  if (![lightness, chroma, hue].every(Number.isFinite) || (alpha !== undefined && !Number.isFinite(alpha))) {
    return undefined;
  }

  const hueRadians = (hue * Math.PI) / 180;
  const a = chroma * Math.cos(hueRadians);
  const b = chroma * Math.sin(hueRadians);

  const lPrime = lightness + 0.3963377774 * a + 0.2158037573 * b;
  const mPrime = lightness - 0.1055613458 * a - 0.0638541728 * b;
  const sPrime = lightness - 0.0894841775 * a - 1.291485548 * b;

  const l = lPrime ** 3;
  const m = mPrime ** 3;
  const s = sPrime ** 3;

  const red = formatRgbChannel(4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s);
  const green = formatRgbChannel(-1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s);
  const blue = formatRgbChannel(-0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s);

  if (alpha === undefined) {
    return `rgb(${red}, ${green}, ${blue})`;
  }

  return `rgba(${red}, ${green}, ${blue}, ${Math.min(1, Math.max(0, alpha))})`;
}

function normalizeColorForJsConsumers(color: string): string {
  return oklchToRgb(color) ?? color;
}

export function themeColorVar(token: string): string {
  return `var(${normalizeColorToken(token)})`;
}

export function readThemeColor(token: string, fallback: string, root?: Element, seen = new Set<string>()): string {
  if (typeof window === "undefined" || typeof document === "undefined" || typeof getComputedStyle === "undefined") {
    return fallback;
  }

  const target = root ?? document.documentElement;
  const normalizedToken = normalizeColorToken(token);

  if (seen.has(normalizedToken)) {
    return fallback;
  }

  seen.add(normalizedToken);

  const value = getComputedStyle(target).getPropertyValue(normalizedToken).trim();

  const alias = /^var\((--[^),\s]+)\)$/.exec(value);
  if (alias) {
    return readThemeColor(alias[1], fallback, target, seen);
  }

  return normalizeColorForJsConsumers(value || fallback);
}

export function getThemeColorPalette(mode: ThemeMode, root?: Element): ThemeColorPalette {
  const fallback = THEME_COLOR_FALLBACKS[mode];
  const read = (token: string, fallbackColor: string) => readThemeColor(token, fallbackColor, root);
  const darkMode = mode === "dark";

  return {
    primary: {
      main: read(darkMode ? "primary-400" : "primary", fallback.primary.main),
      light: read(darkMode ? "primary-300" : "primary-400", fallback.primary.light),
      dark: read(darkMode ? "primary" : "primary-600", fallback.primary.dark),
      contrastText: read(darkMode ? "neutral-950" : "neutral-50", fallback.primary.contrastText),
    },
    secondary: {
      main: read(darkMode ? "secondary-400" : "secondary", fallback.secondary.main),
      light: read(darkMode ? "secondary-300" : "secondary-300", fallback.secondary.light),
      dark: read(darkMode ? "secondary-600" : "secondary-600", fallback.secondary.dark),
      contrastText: read("neutral-950", fallback.secondary.contrastText),
    },
    success: {
      main: read("success-text", fallback.success.main),
      light: read("success-300", fallback.success.light),
      dark: read("success-600", fallback.success.dark),
      contrastText: read(darkMode ? "neutral-950" : "neutral-50", fallback.success.contrastText),
    },
    warning: {
      main: read("warning-text", fallback.warning.main),
      light: read("warning-300", fallback.warning.light),
      dark: read("warning-600", fallback.warning.dark),
      contrastText: read("neutral-950", fallback.warning.contrastText),
    },
    error: {
      main: read("error-text", fallback.error.main),
      light: read("error-300", fallback.error.light),
      dark: read("error-600", fallback.error.dark),
      contrastText: read(darkMode ? "neutral-950" : "neutral-50", fallback.error.contrastText),
    },
    info: {
      main: read("info-text", fallback.info.main),
      light: read("info-300", fallback.info.light),
      dark: read("info-600", fallback.info.dark),
      contrastText: read("neutral-950", fallback.info.contrastText),
    },
    background: {
      default: read("background", fallback.background.default),
      paper: read("foreground", fallback.background.paper),
      card: read("foreground", fallback.background.card),
      header: read("foreground", fallback.background.header),
      tab: read("alt-background", fallback.background.tab),
      tabHover: read("alt-foreground", fallback.background.tabHover),
      input: read("background", fallback.background.input),
      muted: read("alt-foreground", fallback.background.muted),
    },
    text: {
      primary: read("text", fallback.text.primary),
      secondary: read("neutral-text", fallback.text.secondary),
      disabled: read(darkMode ? "neutral-600" : "neutral-400", fallback.text.disabled),
    },
    divider: read("divider", fallback.divider),
    logoBackground: read("alt-foreground", fallback.logoBackground),
    logoText: read("text", fallback.logoText),
  };
}

export function getChartSeriesColor(id: string): string {
  let hash = 0;
  const key = id || "default";

  for (let index = 0; index < key.length; index += 1) {
    hash = (hash << 5) - hash + key.charCodeAt(index);
    hash |= 0;
  }

  const colorIndex = Math.abs(hash) % CHART_SERIES_COUNT + 1;
  return themeColorVar(`chart-${colorIndex}`);
}

export function getChartSurfaceColors(): ChartSurfaceColors {
  return {
    muted: themeColorVar("chart-muted"),
    grid: themeColorVar("chart-grid"),
    tooltipBackground: themeColorVar("chart-tooltip-background"),
    tooltipText: themeColorVar("chart-tooltip-text"),
  };
}
