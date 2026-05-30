import React, { useEffect, useMemo, useState, useCallback } from 'react';
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
import type { UserChannel, TestResult } from '../types';
import { notifierApi, CREDENTIAL_PLACEHOLDER, SENSITIVE_FIELDS } from '../services/api';
import { buildPersonalUrl, maskUrlSecrets, validatePersonalConfig } from '../utils/channelUrls';

const CHANNEL_TYPES = [
  { value: 'email', label: 'Email' },
  { value: 'slack', label: 'Slack' },
  { value: 'teams', label: 'Microsoft Teams' },
  { value: 'discord', label: 'Discord' },
  { value: 'telegram', label: 'Telegram' },
  { value: 'gotify', label: 'Gotify' },
  { value: 'pushover', label: 'Pushover' },
  { value: 'sms', label: 'SMS (Twilio)' },
  { value: 'webhook', label: 'Webhook' },
];

const DEFAULT_CONFIGS: Record<string, Record<string, unknown>> = {
  email: {
    to_email: '',
  },
  slack: {
    webhook_url: '',
  },
  teams: {
    webhook_url: '',
  },
  discord: {
    webhook_url: '',
  },
  sms: {
    to_number: '',
  },
  pushover: {
    user_key: '',
    api_token: '',
  },
  telegram: {
    bot_token: '',
  },
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

interface FormState {
  id: string | null;
  type: string;
  label: string;
  enabled: boolean;
  config: Record<string, unknown>;
}

interface PreviewResult {
  value: string;
  helper?: string;
  error: string;
}

const normalizeConfig = (type: string, config: Record<string, unknown> | null): Record<string, unknown> => {
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

const MyChannels: React.FC = () => {
  const [channels, setChannels] = useState<UserChannel[]>([]);
  const [loadingError, setLoadingError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);
  const [formState, setFormState] = useState<FormState>({
    id: null,
    type: 'email',
    label: '',
    enabled: true,
    config: normalizeConfig('email', {}),
  });
  const [saveError, setSaveError] = useState('');
  const [saving, setSaving] = useState(false);
  const [modifiedFields, setModifiedFields] = useState<Set<string>>(new Set());
  const [testingChannels, setTestingChannels] = useState<Set<string>>(new Set());
  const [testResults, setTestResults] = useState<Map<string, TestResult>>(new Map());

  const usedTypes = useMemo(() => new Set(channels.map((channel) => channel.type)), [channels]);
  const availableTypes = CHANNEL_TYPES.filter((channel) => !usedTypes.has(channel.value));

  const loadChannels = useCallback(async () => {
    try {
      const data = await notifierApi.getUserChannels();
      setChannels(data.channels || []);
      setLoadingError('');
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to load channels';
      setLoadingError(message);
    }
  }, []);

  useEffect(() => {
    loadChannels();
  }, [loadChannels]);

  const openCreateDialog = useCallback(() => {
    const defaultType = availableTypes.length ? availableTypes[0].value : 'email';
    setFormState({
      id: null,
      type: defaultType,
      label: '',
      enabled: true,
      config: normalizeConfig(defaultType, {}),
    });
    setModifiedFields(new Set());
    setSaveError('');
    setDialogOpen(true);
  }, [availableTypes]);

  const openEditDialog = useCallback((channel: UserChannel) => {
    setFormState({
      id: channel.id,
      type: channel.type,
      label: channel.label || '',
      enabled: channel.enabled !== false,
      config: normalizeConfig(channel.type, channel.config),
    });
    setModifiedFields(new Set());
    setSaveError('');
    setDialogOpen(true);
  }, []);

  const handleDelete = useCallback(async (channelId: string) => {
    try {
      await notifierApi.deleteUserChannel(channelId);
      await loadChannels();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to delete channel';
      setLoadingError(message);
    }
  }, [loadChannels]);

  const handleTest = useCallback(async (channelId: string) => {
    setTestingChannels(prev => new Set(prev).add(channelId));
    setTestResults(prev => { const next = new Map(prev); next.delete(channelId); return next; });
    try {
      const result = await notifierApi.testChannel(channelId);
      setTestResults(prev => new Map(prev).set(channelId, result));
      // Auto-clear success messages after 3 seconds
      if (result.status === 'success') {
        setTimeout(() => {
          setTestResults(prev => {
            const next = new Map(prev);
            if (next.get(channelId)?.status === 'success') {
              next.delete(channelId);
            }
            return next;
          });
        }, 3000);
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Test failed';
      setTestResults(prev => new Map(prev).set(channelId, { status: 'failed', message }));
    } finally {
      setTestingChannels(prev => { const next = new Set(prev); next.delete(channelId); return next; });
    }
  }, []);

  const updateConfigField = useCallback((field: string, value: unknown) => {
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
  }, []);

  const handleSensitiveFocus = useCallback((field: string) => {
    // When user clicks into a sensitive field showing the placeholder, clear it so they can type
    setFormState((prev) => {
      const currentValue = String(prev.config[field] || '');
      if (currentValue === CREDENTIAL_PLACEHOLDER) {
        return {
          ...prev,
          config: { ...prev.config, [field]: '' },
        };
      }
      return prev;
    });
    setModifiedFields((prev) => new Set(prev).add(field));
  }, []);

  const handleSensitiveBlur = useCallback((field: string) => {
    // If user clicks away without typing anything, restore the placeholder (credential preserved)
    setFormState((prev) => {
      if (!prev.id) return prev; // New channel -- no placeholder to restore
      const currentValue = String(prev.config[field] || '').trim();
      if (currentValue === '') {
        // Restore the placeholder and remove from modified
        setModifiedFields((mf) => {
          const next = new Set(mf);
          next.delete(field);
          return next;
        });
        return {
          ...prev,
          config: { ...prev.config, [field]: CREDENTIAL_PLACEHOLDER },
        };
      }
      return prev;
    });
  }, []);

  const renderConfigFields = () => {
    const { type, config } = formState;

    if (type === 'email') {
      return (
        <TextField
          label="Email Address"
          value={(config.to_email as string) || ''}
          onChange={(event) => updateConfigField('to_email', event.target.value)}
          fullWidth
          margin="dense"
        />
      );
    }

    if (type === 'slack') {
      return (
        <TextField
          label="Webhook URL"
          value={(config.webhook_url as string) || ''}
          onChange={(event) => updateConfigField('webhook_url', event.target.value)}
          onFocus={() => handleSensitiveFocus('webhook_url')}
          onBlur={() => handleSensitiveBlur('webhook_url')}
          fullWidth
          margin="dense"
          placeholder="https://hooks.slack.com/services/..."
          helperText="Slack incoming webhook URL"
        />
      );
    }

    if (type === 'teams') {
      return (
        <TextField
          label="Webhook URL"
          value={(config.webhook_url as string) || ''}
          onChange={(event) => updateConfigField('webhook_url', event.target.value)}
          onFocus={() => handleSensitiveFocus('webhook_url')}
          onBlur={() => handleSensitiveBlur('webhook_url')}
          fullWidth
          margin="dense"
          placeholder="https://..."
          helperText="Microsoft Teams incoming webhook URL"
        />
      );
    }

    if (type === 'discord') {
      return (
        <TextField
          label="Webhook URL"
          value={(config.webhook_url as string) || ''}
          onChange={(event) => updateConfigField('webhook_url', event.target.value)}
          onFocus={() => handleSensitiveFocus('webhook_url')}
          onBlur={() => handleSensitiveBlur('webhook_url')}
          fullWidth
          margin="dense"
          placeholder="https://discord.com/api/webhooks/..."
          helperText="Discord incoming webhook URL"
        />
      );
    }

    if (type === 'sms') {
      return (
        <TextField
          label="Phone Number"
          value={(config.to_number as string) || ''}
          onChange={(event) => updateConfigField('to_number', event.target.value)}
          fullWidth
          margin="dense"
        />
      );
    }

    if (type === 'pushover') {
      return (
        <>
          <TextField
            label="User Key"
            value={(config.user_key as string) || ''}
            onChange={(event) => updateConfigField('user_key', event.target.value)}
            onFocus={() => handleSensitiveFocus('user_key')}
            onBlur={() => handleSensitiveBlur('user_key')}
            fullWidth
            margin="dense"
          />
          <TextField
            label="API Token"
            type="password"
            value={(config.api_token as string) || ''}
            onChange={(event) => updateConfigField('api_token', event.target.value)}
            onFocus={() => handleSensitiveFocus('api_token')}
            onBlur={() => handleSensitiveBlur('api_token')}
            fullWidth
            margin="dense"
          />
        </>
      );
    }

    if (type === 'telegram') {
      return (
        <TextField
          label="Bot Token"
          type="password"
          value={(config.bot_token as string) || ''}
          onChange={(event) => updateConfigField('bot_token', event.target.value)}
          onFocus={() => handleSensitiveFocus('bot_token')}
          onBlur={() => handleSensitiveBlur('bot_token')}
          fullWidth
          margin="dense"
        />
      );
    }

    if (type === 'gotify') {
      return (
        <>
          <TextField
            label="Host"
            value={(config.host as string) || ''}
            onChange={(event) => updateConfigField('host', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Token"
            type="password"
            value={(config.token as string) || ''}
            onChange={(event) => updateConfigField('token', event.target.value)}
            onFocus={() => handleSensitiveFocus('token')}
            onBlur={() => handleSensitiveBlur('token')}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Port (optional)"
            value={(config.port as string) || ''}
            onChange={(event) => updateConfigField('port', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Path (optional)"
            value={(config.path as string) || ''}
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

    if (type === 'webhook') {
      return (
        <>
          <FormControl fullWidth margin="dense">
            <InputLabel id="webhook-kind-label">Payload Format</InputLabel>
            <Select
              labelId="webhook-kind-label"
              value={(config.kind as string) || 'json'}
              label="Payload Format"
              onChange={(event) => updateConfigField('kind', event.target.value)}
            >
              <MenuItem value="json">JSON</MenuItem>
              <MenuItem value="form">Form</MenuItem>
            </Select>
          </FormControl>
          <TextField
            label="Host"
            value={(config.host as string) || ''}
            onChange={(event) => updateConfigField('host', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Port (optional)"
            value={(config.port as string) || ''}
            onChange={(event) => updateConfigField('port', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Path (optional)"
            value={(config.path as string) || ''}
            onChange={(event) => updateConfigField('path', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Username (optional)"
            value={(config.user as string) || ''}
            onChange={(event) => updateConfigField('user', event.target.value)}
            fullWidth
            margin="dense"
          />
          <TextField
            label="Password (optional)"
            type="password"
            value={(config.password as string) || ''}
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

  const buildPreview = useCallback((): PreviewResult => {
    try {
      // When editing, sensitive fields may contain placeholders -- skip URL preview
      if (formState.id) {
        const hasPlaceholderValues = Object.entries(formState.config).some(
          ([key, value]) => SENSITIVE_FIELDS.has(key) && value === CREDENTIAL_PLACEHOLDER
        );
        if (hasPlaceholderValues) {
          return { value: '', helper: 'Existing credentials will be preserved.', error: '' };
        }
      }
      validatePersonalConfig(formState.type, formState.config);
      if (formState.type === 'email' || formState.type === 'sms') {
        return {
          value: '',
          helper: 'Delivery settings are required to deliver this channel.',
          error: '',
        };
      }
      const url = buildPersonalUrl(formState.type, formState.config);
      return { value: maskUrlSecrets(url), error: '' };
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Invalid configuration';
      return { value: '', error: message };
    }
  }, [formState.type, formState.config, formState.id]);

  const preview = buildPreview();

  const handleSave = useCallback(async () => {
    setSaving(true);
    setSaveError('');
    try {
      const isEditing = Boolean(formState.id);

      // Build config for save: placeholder for unmodified sensitive fields, actual values for modified
      const configToSend: Record<string, unknown> = {};
      for (const [key, value] of Object.entries(formState.config)) {
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

      // For new channels, run full validation; for edits, skip URL validation
      // since placeholder values would fail URL building
      if (!isEditing) {
        validatePersonalConfig(formState.type, configToSend);
      }

      if (formState.id) {
        await notifierApi.updateUserChannel(formState.id, {
          label: formState.label,
          enabled: formState.enabled,
          config: configToSend,
        });
      } else {
        await notifierApi.createUserChannel({
          type: formState.type,
          label: formState.label,
          enabled: formState.enabled,
          config: configToSend,
        });
      }
      setDialogOpen(false);
      await loadChannels();
    } catch (error) {
      const message = error instanceof Error ? error.message : 'Failed to save channel';
      setSaveError(message);
    } finally {
      setSaving(false);
    }
  }, [formState, modifiedFields, loadChannels]);

  const handleTypeChange = useCallback((event: SelectChangeEvent<string>) => {
    const nextType = event.target.value;
    setFormState((prev) => ({
      ...prev,
      type: nextType,
      config: normalizeConfig(nextType, {}),
    }));
  }, []);

  const handleLabelChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setFormState((prev) => ({ ...prev, label: event.target.value }));
  }, []);

  const handleEnabledChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    setFormState((prev) => ({ ...prev, enabled: event.target.checked }));
  }, []);

  const handleCloseDialog = useCallback(() => {
    setDialogOpen(false);
  }, []);

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="body2" color="text.secondary">
          Manage channels for alerts and notifications.
        </Typography>
        <Button
          variant="contained"
          onClick={openCreateDialog}
          disabled={availableTypes.length === 0}
        >
          Add Channel
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
          {channels.map((channel) => {
            const testResult = testResults.get(channel.id);
            const isTesting = testingChannels.has(channel.id);
            return (
              <TableRow key={channel.id}>
                <TableCell sx={{ textTransform: 'capitalize' }}>{channel.type}</TableCell>
                <TableCell>{channel.label || '-'}</TableCell>
                <TableCell>{channel.enabled ? 'Enabled' : 'Disabled'}</TableCell>
                <TableCell>{formatTimestamp(channel.updated_at || channel.created_at)}</TableCell>
                <TableCell align="right">
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: 1, minWidth: 0, mr: 1 }}>
                      <Button
                        size="small"
                        variant="text"
                        color={testResult?.status === 'failed' ? 'error' : 'primary'}
                        onClick={() => handleTest(channel.id)}
                        disabled={isTesting || !channel.enabled}
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
                    <Button size="small" variant="outlined" onClick={() => openEditDialog(channel)}>
                      Edit
                    </Button>
                    <Button
                      size="small"
                      color="error"
                      variant="text"
                      onClick={() => handleDelete(channel.id)}
                    >
                      Delete
                    </Button>
                  </Box>
                </TableCell>
              </TableRow>
            );
          })}
          {channels.length === 0 && (
            <TableRow>
              <TableCell colSpan={5}>
                <Typography variant="body2" color="text.secondary">
                  No channels configured yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={dialogOpen} onClose={handleCloseDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{formState.id ? 'Edit Channel' : 'Add Channel'}</DialogTitle>
        <DialogContent>
          {saveError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {saveError}
            </Alert>
          )}
          <FormControl fullWidth margin="dense" disabled={Boolean(formState.id)}>
            <InputLabel id="channel-type-label">Channel Type</InputLabel>
            <Select
              labelId="channel-type-label"
              value={formState.type}
              label="Channel Type"
              onChange={handleTypeChange}
            >
              {(formState.id ? CHANNEL_TYPES : availableTypes).map((option) => (
                <MenuItem key={option.value} value={option.value}>
                  {option.label}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
          <TextField
            label="Label"
            value={formState.label}
            onChange={handleLabelChange}
            fullWidth
            margin="dense"
            helperText="Optional display name for this channel."
          />
          {renderConfigFields()}
          <FormControlLabel
            control={
              <Switch
                checked={formState.enabled}
                onChange={handleEnabledChange}
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
          <Button onClick={handleCloseDialog} disabled={saving}>
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

export default MyChannels;
