import { useCallback } from 'react';
import { Button } from '@mui/material';
import FileDownloadIcon from '@mui/icons-material/FileDownload';
import * as yaml from 'js-yaml';

interface ConfigData {
  rules?: unknown[];
  destinations?: unknown[];
  ai?: {
    provider?: string;
    ollama?: { url?: string; model?: string };
  };
  [key: string]: unknown;
}

interface DownloadConfigProps {
  configData: ConfigData;
}

function DownloadConfig({ configData }: DownloadConfigProps) {
  const downloadConfigYaml = useCallback(() => {
    try {
      const yamlContent = yaml.dump(configData);
      const blob = new Blob([yamlContent], { type: 'text/yaml' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'config.yaml';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error('Error downloading config:', error);
    }
  }, [configData]);

  return (
    <Button
      variant="outlined"
      size="large"
      startIcon={<FileDownloadIcon />}
      onClick={downloadConfigYaml}
    >
      Download Config
    </Button>
  );
}

export default DownloadConfig;
