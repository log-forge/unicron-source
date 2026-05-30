import React, { useEffect, useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  MenuItem,
  Select,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
  Alert,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import { notifierApi, CREDENTIAL_PLACEHOLDER, SENSITIVE_FIELDS } from '../services/api';
import { buildPresetUrl, maskUrlSecrets, validatePresetConfig } from '../utils/channelUrls';
import type { Preset, TestResult } from '../types';

const PRESET_TYPES = [
  { value: 'email', label: 'Email (SMTP)' },
  { value: 'sms', label: 'SMS (Twilio)' },
  { value: 'slack', label: 'Slack' },
  { value: 'msteams', label: 'Microsoft Teams' },
  { value: 'discord', label: 'Discord' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'gotify', label: 'Gotify' },
  { value: 'webhook', label: 'Webhook' },
];

interface EmailDefaultConfig {
  smtp_host: string;
  smtp_port: string;
  username: string;
  password: string;
  from_email: string;
  mode: string;
}

interface SmsDefaultConfig {
  sid: string;
  token: string;
  from_number: string;
}

interface WebhookUrlConfig {
  webhook_url: string;
}

interface TelegramDefaultConfig {
  bot_token: string;
}

interface GotifyDefaultConfig {
  host: string;
  token: string;
  secure: boolean;
  port: string;
  path: string;
}

interface WebhookDefaultConfig {
  kind: string;
  host: string;
  secure: boolean;
  port: string;
  path: string;
  user: string;
  password: string;
}

interface AdvancedConfig {
  mode: string;
  url: string;
}

type PresetConfig =
  | EmailDefaultConfig
  | SmsDefaultConfig
  | WebhookUrlConfig
  | TelegramDefaultConfig
  | GotifyDefaultConfig
  | WebhookDefaultConfig
  | AdvancedConfig
  | Record<string, unknown>;

const DEFAULT_CONFIGS: Record<string, PresetConfig> = {
  email: {
    smtp_host: '',
    smtp_port: '587',
    username: '',
    password: '',
    from_email: '',
    mode: 'starttls',
  },
  sms: {
    sid: '',
    token: '',
    from_number: '',
  },
  slack: { webhook_url: '' },
  msteams: { webhook_url: '' },
  discord: { webhook_url: '' },
  telegram: { bot_token: '' },
  gotify: {
    host: '',
    token: '',
    secure: true,
    port: '',
    path: '',
  },
  webhook: {
    kind: 'json',
    host: '',
    secure: true,
    port: '',
    path: '',
    user: '',
    password: '',
  },
};

const normalizeConfig = (type: string, config: Record<string, unknown> | null | undefined): PresetConfig => {
  const base = DEFAULT_CONFIGS[type] || {};
  return { ...base, ...(config || {}) };
};

const formatTimestamp = (value: string | null | undefined): string => {
  if (!value) return '';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString();
};

interface FormState {
  id: string | null;
  type: string;
  label: string;
  enabled: boolean;
  config: PresetConfig;
}

interface PreviewResult {
  value: string;
  helper?: string;
  error: string;
}

const Presets: React.FC = () => {
  const [presets, setPresets] = useState<Preset[]>([]);
  const [loadingError, setLoadingError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formState, setFormState] = useState<FormState>({
    id: null,
    type: 'slack',
    label: '',
    enabled: true,
    config: normalizeConfig('slack', {}),
  });
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [modifiedFields, setModifiedFields] = useState<Set<string>>(new Set());
  const [testingPresets, setTestingPresets] = useState<Set<string>>(new Set());
  const [testResults, setTestResults] = useState<Map<string, TestResult>>(new Map());

  const loadPresets = async () => {
    try {
      const data = await notifierApi.getPresets();
      setPresets(data.presets || []);
      setLoadingError('');
    } catch (error) {
      setLoadingError(error instanceof Error ? error.message : 'Failed to load presets');
    }
  };

  useEffect(() => {
    loadPresets();
  }, []);

  const openCreateDialog = () => {
    setFormState({
      id: null,
      type: 'slack',
      label: '',
      enabled: true,
      config: normalizeConfig('slack', {}),
    });
    setModifiedFields(new Set());
    setSaveError('');
    setDialogOpen(true);
  };

  const openEditDialog = (preset: Preset) => {
    setFormState({
      id: preset.id,
      type: preset.type,
      label: preset.label || '',
      enabled: preset.enabled !== false,
      config: normalizeConfig(preset.type, preset.config),
    });
    setModifiedFields(new Set());
    setSaveError('');
    setDialogOpen(true);
  };

  const handleDelete = async (presetId: string) => {
    try {
      await notifierApi.deletePreset(presetId);
      await loadPresets();
    } catch (error) {
      setLoadingError(error instanceof Error ? error.message : 'Failed to delete preset');
    }
  };

  const handleTest = async (presetId: string) => {
    setTestingPresets(prev => new Set(prev).add(presetId));
    setTestResults(prev => { const next = new Map(prev); next.delete(presetId); return next; });
    try {
      const result = await notifierApi.testPreset(presetId);
      setTestResults(prev => new Map(prev).set(presetId, result));
      // Auto-clear success messages after 3 seconds
      if (result.status === 'success') {
        setTimeout(() => {
          setTestResults(prev => {
            const next = new Map(prev);
            if (next.get(presetId)?.status === 'success') {
              next.delete(presetId);
            }
            return next;
          });
        }, 3000);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Test failed';
      setTestResults(prev => new Map(prev).set(presetId, { status: 'failed', message }));
    } finally {
      setTestingPresets(prev => { const next = new Set(prev); next.delete(presetId); return next; });
    }
  };

  const updateConfigField = (field: string, value: unknown) => {
    setFormState((prev) => ({
      ...prev,
      config: {
        ...prev.config,
        [field]: value,
      },
    }));
    if (SENSITIVE_FIELDS.has(field)) {
      setModifiedFields((prev) => new Set(prev).add(field));
    }
  };

  const handleSensitiveFocus = (field: string) => {
    // When user clicks into a sensitive field showing the placeholder, clear it so they can type
    setFormState((prev) => {
      const config = prev.config as Record<string, unknown>;
      const currentValue = String(config[field] || '');
      if (currentValue === CREDENTIAL_PLACEHOLDER) {
        return {
          ...prev,
          config: { ...config, [field]: '' },
        };
      }
      return prev;
    });
    setModifiedFields((prev) => new Set(prev).add(field));
  };

  const handleSensitiveBlur = (field: string) => {
    // If user clicks away without typing anything, restore the placeholder (credential preserved)
    setFormState((prev) => {
      if (!prev.id) return prev; // New preset -- no placeholder to restore
      const config = prev.config as Record<string, unknown>;
      const currentValue = String(config[field] || '').trim();
      if (currentValue === '') {
        // Restore the placeholder and remove from modified
        setModifiedFields((mf) => {
          const next = new Set(mf);
          next.delete(field);
          return next;
        });
        return {
          ...prev,
          config: { ...config, [field]: CREDENTIAL_PLACEHOLDER },
        };
      }
      return prev;
    });
  };

  const supportsAdvanced = !['email', 'sms'].includes(formState.type);
  const configMode = (formState.config as Record<string, unknown>)?.mode;
  const isAdvanced = supportsAdvanced && String(configMode || '').toLowerCase() === 'advanced';

  const renderConfigFields = () => {
    const config = formState.config as Record<string, unknown>;

    if (isAdvanced) {
      return (
        <TextField
          label="Apprise URL"
          value={String(config.url || '')}
          onChange={(event) => updateConfigField('url', event.target.value)}
          fullWidth
          margin="dense"
        />
      );
    }

    if (formState.type === 'email') {
      return (
        <>
          <TextField
            label="SMTP Host"
            value={String(config.smtp_host || '')}
            onChange={(event) => updateConfigField('smtp_host', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="SMTP Port"
            value={String(config.smtp_port || '')}
            onChange={(event) => updateConfigField('smtp_port', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Username"
            value={String(config.username || '')}
            onChange={(event) => updateConfigField('username', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Password"
            type="password"
            value={String(config.password || '')}
            onChange={(event) => updateConfigField('password', event.target.value)}
            onFocus={() => handleSensitiveFocus('password')}
            onBlur={() => handleSensitiveBlur('password')}
            fullWidth
            margin="dense"
          />
          <TextField
            label="From Email (optional)"
            value={String(config.from_email || '')}
            onChange={(event) => updateConfigField('from_email', event.target.value)}
            fullWidth
            margin="dense"
          />
          <FormControl fullWidth margin="dense">
            <InputLabel id="email-mode-label">TLS Mode</InputLabel>
            <Select
              labelId="email-mode-label"
              value={String(config.mode || '')}
              label="TLS Mode"
              onChange={(event: SelectChangeEvent) => updateConfigField('mode', event.target.value)}
            >
              <MenuItem value="">Auto</MenuItem>
              <MenuItem value="starttls">StartTLS</MenuItem>
              <MenuItem value="ssl">SSL</MenuItem>
            </Select>
          </FormControl>
        </>
      );
    }

    if (formState.type === 'sms') {
      return (
        <>
          <TextField
            label="Twilio Account SID"
            value={String(config.sid || '')}
            onChange={(event) => updateConfigField('sid', event.target.value)}
            onFocus={() => handleSensitiveFocus('sid')}
            onBlur={() => handleSensitiveBlur('sid')}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Twilio Auth Token"
            type="password"
            value={String(config.token || '')}
            onChange={(event) => updateConfigField('token', event.target.value)}
            onFocus={() => handleSensitiveFocus('token')}
            onBlur={() => handleSensitiveBlur('token')}
            fullWidth
            margin="dense"
          />
          <TextField
            label="From Number"
            value={String(config.from_number || '')}
            onChange={(event) => updateConfigField('from_number', event.target.value)}
            fullWidth
            margin="dense"
          />
        </>
      );
    }

    if (formState.type === 'slack' || formState.type === 'msteams' || formState.type === 'discord') {
      return (
        <TextField
          label="Webhook URL"
          value={String(config.webhook_url || '')}
          onChange={(event) => updateConfigField('webhook_url', event.target.value)}
          onFocus={() => handleSensitiveFocus('webhook_url')}
          onBlur={() => handleSensitiveBlur('webhook_url')}
          fullWidth
          margin="dense"
        />
      );
    }

    if (formState.type === 'telegram') {
      return (
        <TextField
          label="Bot Token"
          type="password"
          value={String(config.bot_token || '')}
          onChange={(event) => updateConfigField('bot_token', event.target.value)}
          onFocus={() => handleSensitiveFocus('bot_token')}
          onBlur={() => handleSensitiveBlur('bot_token')}
          fullWidth
          margin="dense"
        />
      );
    }

    if (formState.type === 'gotify') {
      return (
        <>
          <TextField
            label="Host"
            value={String(config.host || '')}
            onChange={(event) => updateConfigField('host', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Token"
            type="password"
            value={String(config.token || '')}
            onChange={(event) => updateConfigField('token', event.target.value)}
            onFocus={() => handleSensitiveFocus('token')}
            onBlur={() => handleSensitiveBlur('token')}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Port (optional)"
            value={String(config.port || '')}
            onChange={(event) => updateConfigField('port', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Path (optional)"
            value={String(config.path || '')}
            onChange={(event) => updateConfigField('path', event.target.value)}
            fullWidth
            margin="dense"
          />
          <FormControlLabel
            control={
              <Switch
                checked={config.secure !== false}
                onChange={(event) => updateConfigField('secure', event.target.checked)}
              />
            }
            label="Use HTTPS"
          />
        </>
      );
    }

    if (formState.type === 'webhook') {
      return (
        <>
          <FormControl fullWidth margin="dense">
            <InputLabel id="webhook-kind-label">Webhook Type</InputLabel>
            <Select
              labelId="webhook-kind-label"
              value={String(config.kind || 'json')}
              label="Webhook Type"
              onChange={(event: SelectChangeEvent) => updateConfigField('kind', event.target.value)}
            >
              <MenuItem value="json">JSON</MenuItem>
              <MenuItem value="form">Form</MenuItem>
            </Select>
          </FormControl>
          <TextField
            label="Host"
            value={String(config.host || '')}
            onChange={(event) => updateConfigField('host', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Port (optional)"
            value={String(config.port || '')}
            onChange={(event) => updateConfigField('port', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Path (optional)"
            value={String(config.path || '')}
            onChange={(event) => updateConfigField('path', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Username (optional)"
            value={String(config.user || '')}
            onChange={(event) => updateConfigField('user', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Password (optional)"
            type="password"
            value={String(config.password || '')}
            onChange={(event) => updateConfigField('password', event.target.value)}
            onFocus={() => handleSensitiveFocus('password')}
            onBlur={() => handleSensitiveBlur('password')}
            fullWidth
            margin="dense"
          />
          <FormControlLabel
            control={
              <Switch
                checked={config.secure !== false}
                onChange={(event) => updateConfigField('secure', event.target.checked)}
              />
            }
            label="Use HTTPS"
          />
        </>
      );
    }

    return null;
  };

  const buildPreview = (): PreviewResult => {
    const config = formState.config as Record<string, unknown>;
    try {
      // When editing, sensitive fields may contain placeholders -- skip URL preview
      if (formState.id) {
        const hasPlaceholderValues = Object.entries(config).some(
          ([key, value]) => SENSITIVE_FIELDS.has(key) && value === CREDENTIAL_PLACEHOLDER
        );
        if (hasPlaceholderValues) {
          return { value: '', helper: 'Existing credentials will be preserved.', error: '' };
        }
      }
      validatePresetConfig(formState.type, config);
      if (formState.type === 'email' || formState.type === 'sms') {
        return {
          value: '',
          helper: 'Recipients are chosen per user or group.',
          error: '',
        };
      }
      const url = buildPresetUrl(formState.type, config);
      return { value: maskUrlSecrets(url), error: '' };
    } catch (error) {
      return { value: '', error: error instanceof Error ? error.message : 'Invalid configuration' };
    }
  };

  const preview = buildPreview();

  const handleSave = async () => {
    setSaving(true);
    setSaveError('');
    const config = formState.config as Record<string, unknown>;
    try {
      const isEditing = Boolean(formState.id);

      // Build config for save: placeholder for unmodified sensitive fields, actual values for modified
      const configToSend: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(config)) {
        if (isEditing && SENSITIVE_FIELDS.has(key)) {
          if (modifiedFields.has(key)) {
            // User modified this field -- validate not empty for required fields
            const strValue = String(value || '').trim();
            if (!strValue) {
              throw new Error(`${key.replace(/_/g, ' ')} is required`);
            }
            configToSend[key] = value;
          } else {
            // Unmodified -- send the placeholder to preserve existing credential
            configToSend[key] = CREDENTIAL_PLACEHOLDER;
          }
        } else {
          configToSend[key] = value;
        }
      }

      // For new presets, run full validation; for edits, skip URL validation
      // since placeholder values would fail URL building
      if (!isEditing) {
        validatePresetConfig(formState.type, configToSend);
      }

      if (formState.id) {
        await notifierApi.updatePreset(formState.id, {
          label: formState.label,
          enabled: formState.enabled,
          config: configToSend,
        });
      } else {
        await notifierApi.createPreset({
          type: formState.type,
          label: formState.label,
          enabled: formState.enabled,
          config: configToSend,
        });
      }
      setDialogOpen(false);
      await loadPresets();
    } catch (error) {
      setSaveError(error instanceof Error ? error.message : 'Failed to save preset');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="body2" color="text.secondary">
          Manage preconfigured channels and transports for group notifications.
        </Typography>
        <Button variant="contained" onClick={openCreateDialog}>
          Add Preset
        </Button>
      </Box>

      {loadingError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadingError}
        </Alert>
      )}

      <Table>
        <TableHead>
          <TableRow>
            <TableCell>Type</TableCell>
            <TableCell>Label</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Updated</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {presets.map((preset) => {
            const testResult = testResults.get(preset.id);
            const isTesting = testingPresets.has(preset.id);
            return (
              <TableRow key={preset.id}>
                <TableCell sx={{ textTransform: 'capitalize' }}>{preset.type}</TableCell>
                <TableCell>{preset.label || '-'}</TableCell>
                <TableCell>{preset.enabled ? 'Enabled' : 'Disabled'}</TableCell>
                <TableCell>{formatTimestamp(preset.updated_at || preset.created_at)}</TableCell>
                <TableCell align="right">
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1, minWidth: 0, mr: 1 }}>
                      <Button
                        size="small"
                        variant="text"
                        color={testResult?.status === 'failed' ? 'error' : 'primary'}
                        onClick={() => handleTest(preset.id)}
                        disabled={isTesting || !preset.enabled}
                        sx={{ flexShrink: 0 }}
                      >
                        {isTesting ? 'Testing...' : 'Send Test'}
                      </Button>
                      {testResult && (
                        <Typography
                          variant="caption"
                          title={testResult.message}
                          noWrap
                          sx={{
                            color: testResult.status === 'success' ? 'success.main' : 'error.main',
                            maxWidth: 280,
                            minWidth: 0,
                            textAlign: 'right',
                          }}
                        >
                          {testResult.message}
                        </Typography>
                      )}
                    </Box>
                    <Button size="small" variant="outlined" onClick={() => openEditDialog(preset)}>
                      Edit
                    </Button>
                    <Button
                      size="small"
                      color="error"
                      variant="text"
                      onClick={() => handleDelete(preset.id)}
                    >
                      Delete
                    </Button>
                  </Box>
                </TableCell>
              </TableRow>
            );
          })}
          {presets.length === 0 && (
            <TableRow>
              <TableCell colSpan={5}>
                <Typography variant="body2" color="text.secondary">
                  No presets configured yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{formState.id ? 'Edit Preset' : 'Add Preset'}</DialogTitle>
        <DialogContent>
          {saveError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {saveError}
            </Alert>
          )}
          <FormControl fullWidth margin="dense">
            <InputLabel id="preset-type-label">Preset Type</InputLabel>
            <Select
              labelId="preset-type-label"
              value={formState.type}
              label="Preset Type"
              onChange={(event: SelectChangeEvent) => {
                const nextType = event.target.value;
                setFormState((prev) => ({
                  ...prev,
                  type: nextType,
                  config: normalizeConfig(nextType, {}),
                }));
              }}
            >
              {PRESET_TYPES.map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="Label"
            value={formState.label}
            onChange={(event) => setFormState((prev) => ({ ...prev, label: event.target.value }))}
            fullWidth
            margin="dense"
            helperText="Optional display name for this preset."
          />
          {supportsAdvanced && (
            <FormControlLabel
              control={
                <Switch
                  checked={isAdvanced}
                  onChange={(event) => {
                    const nextValue = event.target.checked;
                    setFormState((prev) => ({
                      ...prev,
                      config: nextValue ? { mode: 'advanced', url: '' } : normalizeConfig(prev.type, {}),
                    }));
                  }}
                />
              }
              label="Advanced URL"
            />
          )}
          {renderConfigFields()}
          <FormControlLabel
            control={
              <Switch
                checked={formState.enabled}
                onChange={(event) => setFormState((prev) => ({ ...prev, enabled: event.target.checked }))}
              />
            }
            label="Enabled"
          />
          {preview.error ? (
            <Typography variant="caption" color="error" sx={{ display: 'block', mt: 1 }}>
              {preview.error}
            </Typography>
          ) : preview.helper ? (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              {preview.helper}
            </Typography>
          ) : (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
              Preview URL: {preview.value}
            </Typography>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)} disabled={saving}>
            Cancel
          </Button>
          <Button variant="contained" onClick={handleSave} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Presets;
