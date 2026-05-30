import {
  Box,
  FormControlLabel,
  Switch,
  TextField,
  Typography
} from '@mui/material';
import type { AISettingsData } from '../../services/api';

interface DefaultRuleProps {
  aiEnabled: boolean;
  preprompt: string;
  onFieldChange: (field: keyof AISettingsData, value: unknown) => void;
}

function DefaultRule({
  aiEnabled,
  preprompt,
  onFieldChange
}: DefaultRuleProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
      <Box>
        <Typography variant="h6" component="h2" gutterBottom={false}>
          AI Enrichment
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
          Enrich notifications with AI summaries, severity assessments, and remediation suggestions.
        </Typography>
      </Box>

      <FormControlLabel
        control={
          <Switch
            checked={aiEnabled}
            onChange={(_e, checked) => onFieldChange('ai_enabled', checked)}
          />
        }
        label="Enable AI processing"
        sx={{
          ml: 0,
          '& .MuiFormControlLabel-label': { fontWeight: 600 }
        }}
      />

      <Box sx={{ opacity: aiEnabled ? 1 : 0.45, transition: 'opacity 0.2s' }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }}>
          Default AI preprompt
        </Typography>

        <TextField
          multiline
          minRows={3}
          maxRows={8}
          value={preprompt}
          onChange={(e) => onFieldChange('ai_default_preprompt', e.target.value)}
          fullWidth
          disabled={!aiEnabled}
          placeholder="You are an AI specialized in analyzing technical documents and logs. Extract and present only the useful details in a clear, concise format. Provide the answer directly without any additional text, greetings, or commentary."
          size="small"
        />

        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: 'block' }}>
          System prompt for Ollama. Rules can override with per-rule preprompts.
        </Typography>
      </Box>
    </Box>
  );
}

export default DefaultRule;
