import {
  Box,
  Typography,
  TextField
} from '@mui/material';
import type { AISettingsData } from '../../services/api';

interface AIProviderProps {
  ollamaUrl: string;
  ollamaModel: string;
  aiTimeout: number;
  aiCacheTtl: number;
  aiEnabled: boolean;
  onFieldChange: (field: keyof AISettingsData, value: unknown) => void;
}

function AIProvider({
  ollamaUrl,
  ollamaModel,
  aiTimeout,
  aiCacheTtl,
  aiEnabled,
  onFieldChange
}: AIProviderProps) {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5, opacity: aiEnabled ? 1 : 0.45, transition: 'opacity 0.2s' }}>
      <Typography variant="h6" component="h2">
        Ollama Configuration
      </Typography>

      <TextField
        label="Ollama URL"
        value={ollamaUrl}
        onChange={(e) => onFieldChange('ollama_url', e.target.value)}
        fullWidth
        disabled={!aiEnabled}
        size="small"
        helperText="API base URL for the Ollama runtime"
      />

      <TextField
        label="Model"
        value={ollamaModel}
        onChange={(e) => onFieldChange('ollama_model', e.target.value)}
        fullWidth
        disabled={!aiEnabled}
        size="small"
        helperText="e.g., gemma3:1b, llama3.2:1b"
      />

      <Box sx={{ display: 'flex', gap: 1.5 }}>
        <TextField
          label="Timeout (s)"
          type="number"
          value={aiTimeout}
          onChange={(e) => onFieldChange('ai_timeout', Number(e.target.value))}
          fullWidth
          disabled={!aiEnabled}
          size="small"
          slotProps={{ htmlInput: { min: 1 } }}
          helperText="Ollama call timeout"
        />
        <TextField
          label="Cache TTL (s)"
          type="number"
          value={aiCacheTtl}
          onChange={(e) => onFieldChange('ai_cache_ttl', Number(e.target.value))}
          fullWidth
          disabled={!aiEnabled}
          size="small"
          slotProps={{ htmlInput: { min: 0 } }}
          helperText="0 to disable cache"
        />
      </Box>
    </Box>
  );
}

export default AIProvider;
