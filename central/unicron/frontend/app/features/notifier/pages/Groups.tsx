import React, { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  ListItemText,
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
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import type { NotificationGroup, GroupTargets, UserChannel } from '../types';
import { notifierApi } from '../services/api';

interface GroupDialogState {
  open: boolean;
  id: string | null;
  name: string;
  enabled: boolean;
  channelIds: string[];
}

const emptyDialog: GroupDialogState = {
  open: false,
  id: null,
  name: '',
  enabled: true,
  channelIds: [],
};

const normalizeTargets = (group?: NotificationGroup): GroupTargets => {
  const targets = group?.target_config || group?.targets || {};
  return {
    channel_ids: targets.channel_ids || [],
    preset_ids: [],
  };
};

const Groups: React.FC = () => {
  const [groups, setGroups] = useState<NotificationGroup[]>([]);
  const [channels, setChannels] = useState<UserChannel[]>([]);
  const [loadingError, setLoadingError] = useState('');
  const [dialog, setDialog] = useState<GroupDialogState>(emptyDialog);
  const [savingError, setSavingError] = useState('');
  const [saving, setSaving] = useState(false);

  const loadData = useCallback(async () => {
    try {
      const [groupsData, channelsData] = await Promise.all([
        notifierApi.getAllGroups(),
        notifierApi.getUserChannels(),
      ]);
      setGroups(groupsData.groups || []);
      setChannels(channelsData.channels || []);
      setLoadingError('');
    } catch (error) {
      setLoadingError(error instanceof Error ? error.message : 'Failed to load groups');
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const channelLabelMap = useMemo(() => {
    const map = new Map<string, string>();
    channels.forEach((channel) => {
      map.set(channel.id, channel.label || `${channel.type} ${channel.id}`);
    });
    return map;
  }, [channels]);

  const openCreateDialog = useCallback(() => {
    setDialog({ ...emptyDialog, open: true });
    setSavingError('');
  }, []);

  const openEditDialog = useCallback((group: NotificationGroup) => {
    const targets = normalizeTargets(group);
    setDialog({
      open: true,
      id: group.id,
      name: group.name || '',
      enabled: group.enabled !== false,
      channelIds: targets.channel_ids || [],
    });
    setSavingError('');
  }, []);

  const closeDialog = useCallback(() => {
    setDialog(emptyDialog);
  }, []);

  const handleDelete = useCallback(
    async (groupId: string) => {
      try {
        await notifierApi.deleteGroup(groupId);
        await loadData();
      } catch (error) {
        setLoadingError(error instanceof Error ? error.message : 'Failed to delete group');
      }
    },
    [loadData]
  );

  const saveGroup = useCallback(async () => {
    setSaving(true);
    setSavingError('');
    try {
      const target_config: GroupTargets = {
        channel_ids: dialog.channelIds,
        preset_ids: [],
      };
      if (dialog.id) {
        await notifierApi.updateGroup(dialog.id, {
          name: dialog.name,
          enabled: dialog.enabled,
          target_config,
        });
      } else {
        await notifierApi.createGroup({
          name: dialog.name,
          enabled: dialog.enabled,
          target_config,
        });
      }
      closeDialog();
      await loadData();
    } catch (error) {
      setSavingError(error instanceof Error ? error.message : 'Failed to save group');
    } finally {
      setSaving(false);
    }
  }, [dialog, loadData, closeDialog]);

  const handleChannelIdsChange = useCallback((event: SelectChangeEvent<string[]>) => {
    const value = event.target.value;
    setDialog((prev) => ({
      ...prev,
      channelIds: typeof value === 'string' ? value.split(',') : value,
    }));
  }, []);

  const formatTargetList = useCallback(
    (ids: string[], labels: Map<string, string>, fallback: string) =>
      ids.length ? ids.map((id) => labels.get(id) || `${fallback} ${id}`).join(', ') : 'None',
    []
  );

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 3 }}>
        <Typography variant="body2" color="text.secondary">
          Create named delivery bundles from direct channels.
        </Typography>
        <Button variant="contained" onClick={openCreateDialog}>
          Add Group
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
            <TableCell>Name</TableCell>
            <TableCell>Status</TableCell>
            <TableCell>Channels</TableCell>
            <TableCell align="right">Actions</TableCell>
          </TableRow>
        </TableHead>
        <TableBody>
          {groups.map((group) => {
            const targets = normalizeTargets(group);
            return (
              <TableRow key={group.id}>
                <TableCell>{group.name || '-'}</TableCell>
                <TableCell>{group.enabled ? 'Enabled' : 'Disabled'}</TableCell>
                <TableCell>
                  {formatTargetList(targets.channel_ids || [], channelLabelMap, 'Channel')}
                </TableCell>
                <TableCell align="right">
                  <Button size="small" variant="outlined" onClick={() => openEditDialog(group)}>
                    Edit
                  </Button>
                  <Button
                    size="small"
                    color="error"
                    variant="text"
                    onClick={() => handleDelete(group.id)}
                    sx={{ ml: 1 }}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            );
          })}
          {groups.length === 0 && (
            <TableRow>
              <TableCell colSpan={4}>
                <Typography variant="body2" color="text.secondary">
                  No groups configured yet.
                </Typography>
              </TableCell>
            </TableRow>
          )}
        </TableBody>
      </Table>

      <Dialog open={dialog.open} onClose={closeDialog} maxWidth="sm" fullWidth>
        <DialogTitle>{dialog.id ? 'Edit Group' : 'Add Group'}</DialogTitle>
        <DialogContent>
          {savingError && (
            <Alert severity="error" sx={{ mb: 2 }}>
              {savingError}
            </Alert>
          )}
          <TextField
            label="Group Name"
            value={dialog.name}
            onChange={(event) => setDialog((prev) => ({ ...prev, name: event.target.value }))}
            fullWidth
            margin="dense"
          />
          <FormControlLabel
            control={
              <Switch
                checked={dialog.enabled}
                onChange={(event) => setDialog((prev) => ({ ...prev, enabled: event.target.checked }))}
              />
            }
            label="Enabled"
          />
          <FormControl fullWidth margin="dense">
            <InputLabel id="group-channels-label">Channels</InputLabel>
            <Select
              labelId="group-channels-label"
              multiple
              value={dialog.channelIds}
              label="Channels"
              onChange={handleChannelIdsChange}
              renderValue={(selected) =>
                selected.map((id) => channelLabelMap.get(id) || `Channel ${id}`).join(', ')
              }
            >
              {channels.map((channel) => (
                <MenuItem key={channel.id} value={channel.id}>
                  <Checkbox checked={dialog.channelIds.includes(channel.id)} />
                  <ListItemText
                    primary={channel.label || `${channel.type} ${channel.id}`}
                    secondary={channel.enabled ? channel.type : `${channel.type} disabled`}
                  />
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </DialogContent>
        <DialogActions>
          <Button onClick={closeDialog} disabled={saving}>
            Cancel
          </Button>
          <Button variant="contained" onClick={saveGroup} disabled={saving}>
            {saving ? 'Saving...' : 'Save'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

export default Groups;
