import { useState, useRef, useEffect, useCallback } from 'react';
import * as yaml from 'js-yaml';
import AceEditor from 'react-ace';
import 'ace-builds/src-noconflict/mode-yaml';
import 'ace-builds/src-noconflict/theme-merbivore_soft';
import 'ace-builds/src-noconflict/ext-language_tools';
import {
  Box,
  TextField,
  FormHelperText,
  Typography,
  IconButton,
  Paper
} from '@mui/material';
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { alpha, useTheme } from '@mui/material/styles';

interface YamlEditorProps {
  data: unknown;
  updateData: (data: unknown) => void;
  referenceText: string;
  title?: string;
  referenceTitle?: string;
  maxLines?: number;
  minLines?: number;
}

function YamlEditor({
  data,
  updateData,
  referenceText,
  title = 'Define in YAML format:',
  referenceTitle = 'Format reference',
  maxLines = 22,
  minLines = 22,
}: YamlEditorProps) {
  const theme = useTheme();
  const [yamlContent, setYamlContent] = useState(() => {
    try {
      return yaml.dump(data || []);
    } catch {
      return '';
    }
  });
  const [yamlError, setYamlError] = useState('');
  const yamlReferenceRef = useRef<HTMLTextAreaElement>(null);

  const handleYamlChange = useCallback((newValue: string) => {
    setYamlContent(newValue);
    try {
      yaml.load(newValue);
      setYamlError('');
    } catch (error) {
      setYamlError(`Invalid YAML: ${error instanceof Error ? error.message : String(error)}`);
    }
  }, []);

  const copyYamlReference = useCallback(() => {
    if (yamlReferenceRef.current) {
      navigator.clipboard.writeText(yamlReferenceRef.current.value);
    }
  }, []);

  useEffect(() => {
    try {
      const parsed = yaml.load(yamlContent);
      if (!yamlError && (yamlContent.trim() === '' || parsed)) {
        updateData(parsed || []);
      }
    } catch {
      // handled via form feedback
    }
  }, [yamlContent, yamlError, updateData]);

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
          {title}
        </Typography>
        <Paper
          elevation={0}
          sx={{
            borderRadius: 2,
            border: `1px solid ${alpha(theme.palette.divider, theme.palette.mode === 'light' ? 0.8 : 0.6)}`,
            overflow: 'hidden',
          }}
        >
          <AceEditor
            mode="yaml"
            theme="merbivore_soft"
            onChange={handleYamlChange}
            value={yamlContent}
            name="yaml-editor"
            editorProps={{ $blockScrolling: true }}
            fontSize={13}
            width="100%"
            height="auto"
            maxLines={maxLines}
            minLines={minLines}
            showPrintMargin={false}
            showGutter
            highlightActiveLine
            setOptions={{
              showLineNumbers: true,
              tabSize: 2,
              useWorker: false,
            }}
          />
        </Paper>
        {yamlError && (
          <Typography variant="body2" color="error">
            {yamlError}
          </Typography>
        )}
      </Box>

      <Paper
        elevation={0}
        sx={{
          borderRadius: 2,
          border: `1px solid ${alpha(theme.palette.divider, theme.palette.mode === 'light' ? 0.8 : 0.6)}`,
          backgroundColor: alpha(
            theme.palette.background.paper,
            theme.palette.mode === 'light' ? 0.9 : 0.6
          ),
          p: 2,
          display: 'flex',
          flexDirection: 'column',
          gap: 1.5,
        }}
      >
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Typography variant="subtitle1" sx={{ fontWeight: 600 }}>
            {referenceTitle}
          </Typography>
          <IconButton size="small" onClick={copyYamlReference}>
            <ContentCopyIcon fontSize="inherit" />
          </IconButton>
        </Box>

        <TextField
          inputRef={yamlReferenceRef}
          multiline
          fullWidth
          minRows={3}
          value={referenceText}
          variant="outlined"
          slotProps={{
            input: {
              readOnly: true,
            },
          }}
          sx={{
            '& .MuiOutlinedInput-root': {
              borderRadius: 2,
              backgroundColor: theme.palette.background.default,
            },
            '& .MuiInputBase-input': {
              fontSize: '12px',
              fontFamily: 'Menlo, Consolas, "Courier New", monospace',
            },
          }}
        />
        <FormHelperText sx={{ mt: -0.5 }}>
          Keep required keys and structure; each entry can be extended as needed.
        </FormHelperText>
      </Paper>
    </Box>
  );
}

export default YamlEditor;
