import { createTheme, alpha, type Theme } from '@mui/material/styles';
import { getThemeColorPalette, type ThemeColorPalette } from '../../utils/theme';

// Extend MUI Palette interface for custom background properties
declare module '@mui/material/styles' {
  interface TypeBackground {
    card: string;
    header: string;
    tab: string;
    tabHover: string;
    input: string;
    muted: string;
  }

  interface Palette {
    logoBackground: string;
    logoText: string;
  }

  interface PaletteOptions {
    logoBackground?: string;
    logoText?: string;
  }
}

// Extend Button props for custom 'action' variant
declare module '@mui/material/Button' {
  interface ButtonPropsVariantOverrides {
    action: true;
  }
}

function withAlpha(color: string, opacity: number): string {
  try {
    return alpha(color, opacity);
  } catch {
    const percentage = Math.round(opacity * 10000) / 100;
    return `color-mix(in oklab, ${color} ${percentage}%, transparent)`;
  }
}

function createNotifierPalette(mode: 'light' | 'dark'): ThemeColorPalette & {
  action: {
    disabled: string;
  };
} {
  const palette = getThemeColorPalette(mode);

  return {
    ...palette,
    action: {
      disabled: withAlpha(palette.text.secondary, 0.3),
    },
  };
}

/**
 * Creates a MUI theme for the notifier feature.
 * Ported from LogForge notifier/web/src/theme.js
 *
 * @param mode - 'light' or 'dark' theme mode
 * @returns MUI Theme object
 */
export function getNotifierTheme(mode: 'light' | 'dark' | undefined): Theme {
  const resolvedMode = mode === 'light' || mode === 'dark' ? mode : 'dark';
  const isLight = resolvedMode === 'light';
  const palette = createNotifierPalette(resolvedMode);

  return createTheme({
    palette: {
      mode: resolvedMode,
      ...palette,
    },
    typography: {
      fontFamily:
        '"Inter", "Segoe UI", "Helvetica Neue", Arial, -apple-system, BlinkMacSystemFont, sans-serif',
      fontSize: 14,
      h1: {
        fontSize: '1.9rem',
        fontWeight: 600,
        letterSpacing: '-0.01em',
      },
      h2: {
        fontSize: '1.5rem',
        fontWeight: 600,
        letterSpacing: '-0.01em',
      },
      h3: {
        fontSize: '1.25rem',
        fontWeight: 600,
      },
      h4: {
        fontSize: '1.125rem',
        fontWeight: 600,
      },
      button: {
        textTransform: 'none',
        fontWeight: 600,
        letterSpacing: '0.01em',
      },
      body2: {
        color: palette.text.secondary,
      },
    },
    shape: {
      borderRadius: 12,
    },
    components: {
      MuiPaper: {
        styleOverrides: {
          root: {
            backgroundColor: palette.background.card,
            borderRadius: 16,
            border: `1px solid ${withAlpha(palette.divider, isLight ? 0.8 : 0.6)}`,
            boxShadow: `0 10px 40px -32px ${withAlpha(palette.text.primary, 0.65)}`,
          },
        },
      },
      MuiAppBar: {
        styleOverrides: {
          root: {
            backgroundColor: palette.background.header,
            color: palette.text.primary,
            border: `1px solid ${withAlpha(palette.divider, 0.8)}`,
            boxShadow: `0 10px 32px -30px ${withAlpha(palette.text.primary, 0.7)}`,
          },
        },
      },
      MuiToolbar: {
        styleOverrides: {
          gutters: {
            paddingLeft: 20,
            paddingRight: 20,
            '@media (min-width:900px)': {
              paddingLeft: 28,
              paddingRight: 28,
            },
          },
        },
      },
      MuiTabs: {
        styleOverrides: {
          root: {
            minHeight: 44,
          },
          indicator: {
            height: 3,
            borderRadius: 3,
            backgroundColor: palette.primary.main,
          },
        },
      },
      MuiTab: {
        styleOverrides: {
          root: {
            minHeight: 44,
            fontWeight: 600,
            fontSize: '0.95rem',
            color: palette.text.secondary,
            '&.Mui-selected': {
              color: palette.text.primary,
            },
          },
        },
      },
      MuiButton: {
        styleOverrides: {
          root: {
            borderRadius: 999,
            padding: '8px 18px',
          },
          contained: {
            boxShadow: 'none',
            '&:hover': {
              boxShadow: 'none',
            },
          },
          outlined: {
            borderColor: withAlpha(palette.primary.main, 0.4),
            '&:hover': {
              borderColor: palette.primary.main,
              backgroundColor: withAlpha(palette.primary.main, isLight ? 0.08 : 0.16),
            },
          },
        },
        variants: [
          {
            props: { variant: 'action' },
            style: {
              fontSize: '0.82rem',
              padding: '6px 12px',
              marginLeft: 6,
              backgroundColor: palette.background.muted,
              color: palette.text.primary,
              border: `1px solid ${withAlpha(palette.divider, 0.8)}`,
              '&:hover': {
                backgroundColor: withAlpha(palette.primary.main, 0.12),
              },
            },
          },
        ],
      },
      MuiTableContainer: {
        styleOverrides: {
          root: {
            borderRadius: 16,
            border: `1px solid ${withAlpha(palette.divider, 0.9)}`,
          },
        },
      },
      MuiTableCell: {
        styleOverrides: {
          root: {
            borderColor: withAlpha(palette.divider, isLight ? 0.9 : 0.6),
            padding: '12px 16px',
            fontSize: '0.92rem',
          },
          head: {
            fontWeight: 600,
            letterSpacing: 0,
            backgroundColor: palette.background.muted,
          },
        },
      },
      MuiInputBase: {
        styleOverrides: {
          root: {
            borderRadius: 10,
            backgroundColor: palette.background.input,
            '&.Mui-disabled': {
              backgroundColor: palette.background.muted,
              color: palette.text.disabled,
            },
          },
          input: {
            padding: '10px 12px',
          },
        },
      },
      MuiOutlinedInput: {
        styleOverrides: {
          notchedOutline: {
            borderColor: withAlpha(palette.divider, 0.7),
          },
          root: {
            '&:hover .MuiOutlinedInput-notchedOutline': {
              borderColor: withAlpha(palette.primary.main, 0.8),
            },
            '&.Mui-focused .MuiOutlinedInput-notchedOutline': {
              borderColor: palette.primary.main,
              borderWidth: 1.5,
            },
          },
        },
      },
      MuiSnackbarContent: {
        styleOverrides: {
          root: {
            borderRadius: 12,
          },
        },
      },
    },
  });
}
