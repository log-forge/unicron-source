import { useMemo } from 'react';
import { ScopedCssBaseline, ThemeProvider } from '@mui/material';
import { getNotifierTheme } from '../theme';
import { useTheme } from '~/context/ThemeContext';

interface NotifierThemeProviderProps {
  children: React.ReactNode;
}

export function NotifierThemeProvider({ children }: NotifierThemeProviderProps) {
  const { actualTheme } = useTheme();
  const theme = useMemo(() => getNotifierTheme(actualTheme), [actualTheme]);

  return (
    <ThemeProvider theme={theme}>
      <ScopedCssBaseline
        enableColorScheme
        sx={{
          minHeight: 0,
          backgroundColor: 'transparent',
          color: 'text.primary',
          '& a': {
            color: 'primary.main',
            textDecoration: 'none',
            '&:hover': {
              color: 'primary.dark',
              textDecoration: 'underline',
            },
          },
          '& pre': {
            whiteSpace: 'pre-wrap',
            wordWrap: 'break-word',
            backgroundColor: 'background.muted',
            padding: '10px 12px',
            borderRadius: 1,
            fontSize: '0.9em',
            maxHeight: 220,
            overflowY: 'auto',
          },
        }}
      >
        {children}
      </ScopedCssBaseline>
    </ThemeProvider>
  );
}
