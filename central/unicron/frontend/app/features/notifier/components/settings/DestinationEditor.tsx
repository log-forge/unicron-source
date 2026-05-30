import { useCallback } from 'react';
import YamlEditor from './YamlEditor';

interface Destination {
  name: string;
  enabled?: boolean;
  url: string;
}

interface ConfigData {
  destinations?: Destination[];
  [key: string]: unknown;
}

interface DestinationEditorProps {
  destinations: Destination[];
  updateConfig: (updater: (prev: ConfigData) => ConfigData) => void;
}

function DestinationEditor({ destinations, updateConfig }: DestinationEditorProps) {
  const destinationsReference = `- name: 'Telegram'                    # application name (refer to https://github.com/caronc/apprise/wiki for supported applications and how to configure them)
  enabled: false                      # whether destination should be disabled (global setting, overrides custom rules)
  url: 'tgram://{token}/{chat_id}'    # apprise compatible url with tokens e.g. for telegram refer to (https://github.com/caronc/apprise/wiki/Notify_telegram)`;

  const handleDestinationsUpdate = useCallback(
    (updatedDestinations: unknown) => {
      updateConfig((prev) => ({
        ...prev,
        destinations: updatedDestinations as Destination[]
      }));
    },
    [updateConfig]
  );

  return (
    <YamlEditor
      data={destinations}
      updateData={handleDestinationsUpdate}
      referenceText={destinationsReference}
      referenceTitle="Destination Format Reference"
      title="Define your notification destinations in YAML format:"
    />
  );
}

export default DestinationEditor;
