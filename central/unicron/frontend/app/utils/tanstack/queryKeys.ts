export const HERALD_LIST_QUERY_KEY = ["heralds"] as const;
export const HERALD_SUMMARY_QUERY_KEY = ["heralds", "summary"] as const;
export const HERALD_INVENTORY_QUERY_KEY = ["telemetry", "inventory", "herald"] as const;
export const TELEMETRY_LOGS_QUERY_KEY = ["telemetry", "logs"] as const;
export const TELEMETRY_METRICS_QUERY_KEY = ["telemetry", "metrics"] as const;

export const TELEMETRY_METRICS_LABEL_NAMES_KEY = ["telemetry", "metrics", "labels", "names"] as const;
export const TELEMETRY_METRICS_LABEL_VALUES_KEY = ["telemetry", "metrics", "labels", "values"] as const;

export const victoriaLogsQueryKey = (payload: unknown) => [...TELEMETRY_LOGS_QUERY_KEY, payload] as const;

export const victoriaMetricsQueryKey = (payload: unknown, shape: string) => [...TELEMETRY_METRICS_QUERY_KEY, "instant", shape, payload] as const;

export const victoriaMetricsRangeQueryKey = (payload: unknown, shape: string) => [...TELEMETRY_METRICS_QUERY_KEY, "range", shape, payload] as const;

export const victoriaMetricsLabelNamesKey = (payload: unknown) => [...TELEMETRY_METRICS_LABEL_NAMES_KEY, payload] as const;

export const victoriaMetricsLabelValuesKey = (payload: unknown) => [...TELEMETRY_METRICS_LABEL_VALUES_KEY, payload] as const;
