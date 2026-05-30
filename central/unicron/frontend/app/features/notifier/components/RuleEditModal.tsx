import React, { useState, useEffect } from 'react';
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  FormControlLabel,
  Checkbox,
  Typography,
  Box,
} from '@mui/material';

/**
 * Notification rule notify configuration
 */
interface NotifyConfig {
  destinations?: string[];
  send_og_text?: {
    enabled: boolean;
    og_text_regex?: string;
    ai_text_regex?: string;
  };
  send_ai_text?: {
    enabled: boolean;
    og_text_regex?: string;
    ai_text_regex?: string;
  };
}

/**
 * Notification rule interface for editing
 */
export interface NotificationRule {
  name: string;
  enabled: boolean;
  preprompt?: string;
  match?: {
    sources?: string[];
    og_text_regex?: string;
    ai_text_regex?: string;
  };
  notify?: NotifyConfig;
}

/**
 * RuleEditModal component props
 */
interface RuleEditModalProps {
  open: boolean;
  rule: NotificationRule | null;
  onClose: () => void;
  onSave: (rule: NotificationRule) => void;
}

/**
 * Modal dialog for editing notification rule enable/disable state.
 * Ported from LogForge notifier/web/src/components/RuleEditModal/RuleEditModal.jsx
 */
const RuleEditModal: React.FC<RuleEditModalProps> = ({
  open,
  rule,
  onClose,
  onSave,
}) => {
  const [enabled, setEnabled] = useState<boolean>(rule?.enabled ?? true);

  useEffect(() => {
    setEnabled(rule?.enabled ?? true);
  }, [rule, open]);

  if (!open || !rule) return null;

  const destination = rule.notify?.destinations?.[0] || 'Destination';

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="xs"
      fullWidth
      PaperProps={{
        sx: (theme) => ({
          bgcolor: theme.palette.background.paper,
          color: theme.palette.text.primary,
          borderRadius: 2,
        }),
      }}
    >
      <DialogTitle sx={{ fontWeight: 600, pb: 0 }}>
        Rule for {destination}
      </DialogTitle>
      <DialogContent sx={{ pt: 2 }}>
        <Typography variant="body1" sx={{ mb: 2, color: 'text.primary' }}>
          <b>What does this rule do?</b>
          <br />
          Every notification will be forwarded to{' '}
          <Box component="span" sx={{ color: 'info.main' }}>
            {rule.notify?.destinations?.[0] || 'the selected destination'}
          </Box>
          .
        </Typography>

        <Box sx={{ mb: 3 }}>
          <FormControlLabel
            control={
              <Checkbox
                checked={enabled}
                sx={{
                  color: 'info.main',
                  '&.Mui-checked': { color: 'info.main' },
                }}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) =>
                  setEnabled(e.target.checked)
                }
              />
            }
            label={<span style={{ fontWeight: 500 }}>Enable this rule</span>}
          />
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} sx={{ color: 'text.secondary' }}>
          Cancel
        </Button>
        <Button
          variant="contained"
          onClick={() => onSave({ ...rule, enabled })}
          sx={{
            bgcolor: 'info.main',
            color: 'info.contrastText',
            fontWeight: 600,
            borderRadius: 2,
            boxShadow: 'none',
            ':hover': { bgcolor: 'info.main' },
          }}
        >
          Save
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default RuleEditModal;
