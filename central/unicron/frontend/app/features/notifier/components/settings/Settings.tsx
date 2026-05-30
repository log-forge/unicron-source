import { useState, useEffect, useCallback } from 'react';
import {
  Box,
  Button,
  CircularProgress,
  Snackbar,
  Alert,
  styled,
  Grid,
  Paper
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import DefaultRule from './DefaultRule';
import AIProvider from './AIProvider';
import { notifierApi, type AISettingsData } from '../../services/api';

interface SnackbarState {
  open: boolean;
  message: string;
  severity: 'success' | 'error' | 'warning' | 'info';
}

const DEFAULT_SETTINGS: AISettingsData = {
  ai_enabled: false,
  ollama_url: 'http://ollama:11434',
  ollama_model: 'gemma3:1b',
  ai_timeout: 15,
  ai_cache_ttl: 3600,
  ai_default_preprompt: '',
  has_overrides: false,
};

const SectionCard = styled(Paper)(({ theme }) => ({
  padding: theme.spacing(2.5),
  borderRadius: (theme.shape.borderRadius as number) + 4,
  border: `1px solid ${alpha(theme.palette.divider, theme.palette.mode === 'light' ? 0.8 : 0.6)}`,
  backgroundColor: theme.palette.background.paper,
  height: '100%',
}));

function Settings() {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [settings, setSettings] = useState<AISettingsData>(DEFAULT_SETTINGS);
  const [snackbar, setSnackbar] = useState<SnackbarState>({
    open: false,
    message: '',
    severity: 'success'
  });

  const fetchSettings = useCallback(async () => {
    try {
      setLoading(true);
      const data = await notifierApi.getAISettings();
      setSettings(data);
    } catch (error) {
      // Use defaults if API fails — toggle still works
      setSettings(DEFAULT_SETTINGS);
      setSnackbar({
        open: true,
        message: `Failed to load settings: ${error instanceof Error ? error.message : String(error)}`,
        severity: 'error'
      });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const handleFieldChange = useCallback((field: keyof AISettingsData, value: unknown) => {
    setSettings((prev) => ({ ...prev, [field]: value }));
  }, []);

  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();

      setSaving(true);
      try {
        const updated = await notifierApi.updateAISettings({
          ai_enabled: settings.ai_enabled,
          ollama_url: settings.ollama_url,
          ollama_model: settings.ollama_model,
          ai_timeout: settings.ai_timeout,
          ai_cache_ttl: settings.ai_cache_ttl,
          ai_default_preprompt: settings.ai_default_preprompt,
        });
        setSettings(updated);
        setSnackbar({
          open: true,
          message: 'Settings saved successfully',
          severity: 'success'
        });
      } catch (error) {
        setSnackbar({
          open: true,
          message: `Failed to save settings: ${error instanceof Error ? error.message : String(error)}`,
          severity: 'error'
        });
      } finally {
        setSaving(false);
      }
    },
    [settings]
  );

  const handleCloseSnackbar = useCallback(() => {
    setSnackbar((prev) => ({ ...prev, open: false }));
  }, []);

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
        <CircularProgress />
      </Box>
    );
  }

  return (
    <Box
      component="form"
      onSubmit={handleSubmit}
      sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}
    >
      <Grid container spacing={2.5} alignItems="stretch">
        <Grid size={{ xs: 12, md: 7 }}>
          <SectionCard elevation={0}>
            <DefaultRule
              aiEnabled={settings.ai_enabled}
              preprompt={settings.ai_default_preprompt}
              onFieldChange={handleFieldChange}
            />
          </SectionCard>
        </Grid>
        <Grid size={{ xs: 12, md: 5 }}>
          <SectionCard elevation={0}>
            <AIProvider
              ollamaUrl={settings.ollama_url}
              ollamaModel={settings.ollama_model}
              aiTimeout={settings.ai_timeout}
              aiCacheTtl={settings.ai_cache_ttl}
              aiEnabled={settings.ai_enabled}
              onFieldChange={handleFieldChange}
            />
          </SectionCard>
        </Grid>
      </Grid>

      <Button variant="contained" type="submit" disabled={saving} sx={{ alignSelf: 'flex-start', minWidth: 140 }}>
        {saving ? 'Saving...' : 'Save Settings'}
      </Button>

      <Snackbar open={snackbar.open} autoHideDuration={6000} onClose={handleCloseSnackbar}>
        <Alert onClose={handleCloseSnackbar} severity={snackbar.severity} sx={{ width: '100%' }}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </Box>
  );
}

export default Settings;
