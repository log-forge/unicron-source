export type TelemetryRetentionRow = {
  key: "metrics" | "logs";
  label: string;
  value: string;
};

export type TelemetryStorageLimitControl = {
  key: "metrics-storage-limit" | "logs-storage-limit";
  label: string;
  value: string;
  unit: string;
  disabled: boolean;
};

export type TelemetryStorageSettings = {
  canSave: boolean;
  retention: TelemetryRetentionRow[];
  storageLimits: TelemetryStorageLimitControl[];
};

export function buildTelemetryStorageSettings(): TelemetryStorageSettings {
  return {
    canSave: false,
    retention: [
      { key: "metrics", label: "Metrics retention", value: "7 days" },
      { key: "logs", label: "Logs retention", value: "7 days" },
    ],
    storageLimits: [
      {
        key: "metrics-storage-limit",
        label: "Metrics storage limit",
        value: "No cap",
        unit: "bytes",
        disabled: true,
      },
      {
        key: "logs-storage-limit",
        label: "Logs storage limit",
        value: "No cap",
        unit: "bytes",
        disabled: true,
      },
    ],
  };
}
