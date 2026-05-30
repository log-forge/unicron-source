import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { feDebug } from '../constants';
import { apiService } from '../services/api';
import { globalWebSocket } from '../services/websocket';
import type { AlertRule, Alert, AlertsMeta, AlertsPayload, ContainerInfo, GroupInfo, HealthStatus } from '../types';

// Query keys for TanStack Query cache
const RULES_QUERY_KEY = ['alert-engine', 'rules'] as const;
const ALERTS_QUERY_KEY_PREFIX = ['alert-engine', 'alerts'] as const;
const CONTAINERS_QUERY_KEY = ['alert-engine', 'containers'] as const;
const HEALTH_QUERY_KEY = ['alert-engine', 'health'] as const;

const getAlertsQueryKey = (limit?: number) =>
  [...ALERTS_QUERY_KEY_PREFIX, limit ?? 'default'] as const;

const DEFAULT_HOST_ID = 'local';

const normalizeHostId = (hostId?: string | null): string => {
  if (!hostId) return DEFAULT_HOST_ID;
  return hostId;
};

const buildContainerKey = (name: string, hostId?: string | null): string => {
  return `${normalizeHostId(hostId)}:${name}`;
};

const normalizeContainer = (item: any): ContainerInfo => {
  const name = item?.name || item?.container_name || 'unknown';
  const hostId = normalizeHostId(item?.host_id || item?.hostId);
  const containerKey = item?.container_key || item?.identifier || `${hostId}:${name}`;
  const identifier = containerKey;

  return {
    identifier,
    name,
    host_id: hostId,
    container_key: containerKey,
    docker_container_id: item?.docker_container_id || null,
    monitoring_enabled: Boolean(item?.monitoring_enabled),
    image_name: item?.image_name || item?.image || '',
    last_seen: item?.last_seen || new Date().toISOString(),
    status: item?.status || undefined,
    labels: item?.labels || {},
  };
};

const normalizeContainers = (src: any): ContainerInfo[] => {
  const arr = Array.isArray(src) ? src : Object.values(src || {});
  return arr.map(normalizeContainer);
};

const normalizeGroup = (raw: any): GroupInfo => {
  const members = Array.isArray(raw?.members)
    ? raw.members
        .map((member: any) => {
          if (!member) return null;
          const hostId = normalizeHostId(member?.host_id || member?.hostId);
          const containerName = member?.container_name || member?.containerName || member?.containerKey || member?.container_key;
          if (!containerName) return null;
          return { host_id: hostId, container_name: containerName };
        })
        .filter(Boolean)
    : [];

  const memberKeys = members.map((member: any) => buildContainerKey(member.container_name, member.host_id));
  const legacyIds = Array.isArray(raw?.containerIds)
    ? raw.containerIds
    : Array.isArray(raw?.containerNames)
      ? raw.containerNames
      : [];
  const containerIds = memberKeys.length > 0
    ? memberKeys
    : legacyIds.map((id: string) => (id.includes(':') ? id : buildContainerKey(id, DEFAULT_HOST_ID)));

  return {
    groupId: raw?.groupId ?? raw?.id ?? 0,
    name: raw?.name ?? raw?.groupName ?? '',
    containerIds,
    members: members.length > 0 ? members : undefined,
    monitoredContainerCount: raw?.monitoredContainerCount,
    monitoredContainers: raw?.monitoredContainers ?? containerIds,
  };
};

export function useRules() {
  const queryClient = useQueryClient();

  // Main query for fetching rules with caching
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: RULES_QUERY_KEY,
    queryFn: async () => {
      const response = await apiService.getRules();
      const rules: AlertRule[] = response.rules ?? [];
      const count = response.count ?? 0;
      const max = response.maxRules ?? null;
      const hostCount = response.hostCount;
      const rulesPerHost = response.rulesPerHost;

      if (feDebug()) console.log('FETCHED RULES:', rules.map((r) => ({ id: r.id, name: r.name, enabled: r.enabled, template: !!(r as any).template_source })));
      if (feDebug()) console.log('BACKEND RULE COUNT:', count, 'MAX:', max, 'HOSTS:', hostCount, 'RULES_PER_HOST:', rulesPerHost);

      return { rules, count, maxRules: max, hostCount, rulesPerHost };
    },
    staleTime: 30 * 1000, // Consider data stale after 30s
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
  });

  // Helper: snapshot current cache for optimistic rollback
  type RulesCache = typeof data;
  const snapshotAndCancel = async () => {
    await queryClient.cancelQueries({ queryKey: RULES_QUERY_KEY });
    return queryClient.getQueryData<RulesCache>(RULES_QUERY_KEY);
  };

  // Mutation for creating rules (optimistic: bump count immediately)
  const createMutation = useMutation({
    mutationFn: (rule: Omit<AlertRule, 'id'>) => apiService.createRule(rule),
    onMutate: async (newRule) => {
      const previous = await snapshotAndCancel();
      // Optimistic: add a temporary rule to the list so UI feels instant
      const tempId = `temp-${Date.now()}`;
      const tempRule = { ...newRule, id: tempId } as AlertRule;
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) {
          return { rules: [tempRule], count: 1, maxRules: null, hostCount: undefined, rulesPerHost: undefined };
        }
        return { ...old, rules: [...old.rules, tempRule], count: old.count + 1 };
      });
      return { previous, tempId };
    },
    onSuccess: (createdRule, _vars, context) => {
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) {
          return { rules: [createdRule], count: 1, maxRules: null, hostCount: undefined, rulesPerHost: undefined };
        }

        if (!context?.tempId) {
          return {
            ...old,
            rules: [...old.rules, createdRule],
            count: old.count + 1,
          };
        }

        return {
          ...old,
          rules: old.rules.map((rule) => (rule.id === context.tempId ? createdRule : rule)),
        };
      });
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(RULES_QUERY_KEY, context.previous);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    },
  });

  // Mutation for updating rules (optimistic: merge updates into cached rule)
  const updateMutation = useMutation({
    mutationFn: ({ id, rule }: { id: string; rule: Partial<AlertRule> }) => apiService.updateRule(id, rule),
    onMutate: async ({ id, rule }) => {
      const previous = await snapshotAndCancel();
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) return old;
        return {
          ...old,
          rules: old.rules.map((r) => (r.id === id ? { ...r, ...rule } : r)),
        };
      });
      return { previous };
    },
    onSuccess: (updatedRule) => {
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) {
          return { rules: [updatedRule], count: 1, maxRules: null, hostCount: undefined, rulesPerHost: undefined };
        }

        return {
          ...old,
          rules: old.rules.map((rule) => (rule.id === updatedRule.id ? updatedRule : rule)),
        };
      });
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(RULES_QUERY_KEY, context.previous);
    },
    onSettled: () => {
      void queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    },
  });

  // Mutation for deleting rules (optimistic: remove from list immediately)
  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiService.deleteRule(id),
    onMutate: async (id) => {
      const previous = await snapshotAndCancel();
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) return old;
        return {
          ...old,
          rules: old.rules.filter((r) => r.id !== id),
          count: Math.max(0, old.count - 1),
        };
      });
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) queryClient.setQueryData(RULES_QUERY_KEY, context.previous);
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY }),
  });

  // Mutation for toggling rule enabled state (optimistic: flip instantly)
  const toggleMutation = useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) => {
      if (feDebug()) console.log('TOGGLE START:', { id, enabled });
      return apiService.toggleRuleEnabled(id, enabled);
    },
    onMutate: async ({ id, enabled }) => {
      const previous = await snapshotAndCancel();
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) return old;
        return {
          ...old,
          rules: old.rules.map((r) => (r.id === id ? { ...r, enabled } : r)),
        };
      });
      return { previous };
    },
    onError: (err, _vars, context) => {
      console.error('TOGGLE ERROR:', err);
      if (context?.previous) queryClient.setQueryData(RULES_QUERY_KEY, context.previous);
    },
    onSettled: () => {
      if (feDebug()) console.log('API CALL COMPLETE, invalidating cache');
      queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    },
  });

  // Mutation for bulk toggling rules (optimistic: update all at once)
  const bulkToggleMutation = useMutation({
    mutationFn: ({ ruleIds, enabled }: { ruleIds: string[]; enabled: boolean }) => {
      if (feDebug()) console.log('BULK TOGGLE START:', { ruleIds, enabled });
      return apiService.bulkToggleRules(ruleIds, enabled);
    },
    onMutate: async ({ ruleIds, enabled }) => {
      const previous = await snapshotAndCancel();
      queryClient.setQueryData<RulesCache>(RULES_QUERY_KEY, (old) => {
        if (!old) return old;
        return {
          ...old,
          rules: old.rules.map((r) => (ruleIds.includes(r.id) ? { ...r, enabled } : r)),
        };
      });
      return { previous };
    },
    onError: (err, _vars, context) => {
      console.error('BULK TOGGLE ERROR:', err);
      if (context?.previous) queryClient.setQueryData(RULES_QUERY_KEY, context.previous);
    },
    onSettled: () => {
      if (feDebug()) console.log('BULK TOGGLE COMPLETE, invalidating cache');
      queryClient.invalidateQueries({ queryKey: RULES_QUERY_KEY });
    },
  });

  // Update rules from external source (sets cache directly)
  const updateRules = (newRules: AlertRule[]) => {
    queryClient.setQueryData(RULES_QUERY_KEY, (old: typeof data) => ({
      rules: newRules,
      count: old?.count ?? newRules.length,
      maxRules: old?.maxRules ?? null,
    }));
  };

  // Update rule count from external source
  const updateRuleCount = (count: number) => {
    queryClient.setQueryData(RULES_QUERY_KEY, (old: typeof data) => ({
      rules: old?.rules ?? [],
      count,
      maxRules: old?.maxRules ?? null,
    }));
  };

  return {
    rules: data?.rules ?? [],
    loading: isLoading,
    error: error?.message ?? null,
    fetchRules: refetch,
    createRule: createMutation.mutateAsync,
    updateRule: (id: string, rule: Partial<AlertRule>) => updateMutation.mutateAsync({ id, rule }),
    deleteRule: deleteMutation.mutateAsync,
    toggleRuleEnabled: (id: string, enabled: boolean) => toggleMutation.mutateAsync({ id, enabled }),
    bulkToggle: (ruleIds: string[], enabled: boolean) => bulkToggleMutation.mutateAsync({ ruleIds, enabled }),
    updateRules,
    updateRuleCount,
    ruleCount: data?.count ?? 0,
    maxRules: data?.maxRules ?? null,
    hostCount: data?.hostCount,
    rulesPerHost: data?.rulesPerHost,
  };
}

const DEFAULT_ALERTS_META: AlertsMeta = {
  limit: null,
  requestedLimit: null,
  hasMore: false,
  totalAvailable: null,
  edition: 'source_available',
};

export function useAlerts(limit?: number) {
  const queryClient = useQueryClient();
  const [wsConnected, setWsConnected] = useState(false);
  const alertsQueryKey = getAlertsQueryKey(limit);

  // Main query for fetching alerts with caching
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: alertsQueryKey,
    queryFn: () => apiService.getAlertsPayload(limit),
    staleTime: 30 * 1000, // Consider data stale after 30s
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
  });

  const alerts = data?.alerts ?? [];
  const alertsMeta = data?.meta ?? DEFAULT_ALERTS_META;

  // Mutation for acknowledging an alert
  const acknowledgeMutation = useMutation({
    mutationFn: ({ alertId, comment }: { alertId: string; comment?: string }) =>
      apiService.acknowledgeAlert(alertId, comment),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_PREFIX }),
  });

  // For WebSocket updates, use setQueryData to add to cache
  const addAlert = (newAlert: Alert) => {
    queryClient.setQueryData(alertsQueryKey, (old: AlertsPayload | undefined) => {
      if (!old) return old;

      // Check for duplicate
      const isDuplicate = old.alerts.some(existingAlert =>
        existingAlert.id === newAlert.id ||
        (existingAlert.rule_id === newAlert.rule_id &&
         existingAlert.timestamp === newAlert.timestamp &&
         existingAlert.message === newAlert.message)
      );

      if (isDuplicate) {
        if (feDebug()) console.log('[useAlerts] Duplicate alert prevented:', newAlert);
        return old;
      }

      if (feDebug()) console.log('[useAlerts] Adding new alert:', newAlert);

      const limit = old.meta.limit;
      const updated = [newAlert, ...old.alerts];

      // Check if we're hitting the limit
      const willTrim = limit != null && limit > 0 && updated.length > limit;
      const trimmed = willTrim ? updated.slice(0, limit) : updated;

      return {
        alerts: trimmed,
        meta: {
          ...old.meta,
          totalAvailable: old.meta.totalAvailable != null ? old.meta.totalAvailable + 1 : old.meta.totalAvailable,
          hasMore: willTrim ? true : old.meta.hasMore,
        },
      };
    });
  };

  // Update alerts from external source (sets cache directly)
  const updateAlerts = (payload: AlertsPayload | Alert[]) => {
    if (Array.isArray(payload)) {
      queryClient.setQueryData(alertsQueryKey, (old: AlertsPayload | undefined) => ({
        alerts: payload,
        meta: old?.meta ?? DEFAULT_ALERTS_META,
      }));
    } else {
      queryClient.setQueryData(alertsQueryKey, payload);
    }
  };

  // Update single alert status from WebSocket (real-time sync across tabs)
  const updateAlertStatus = (alertId: string, newStatus: string) => {
    queryClient.setQueryData(alertsQueryKey, (old: AlertsPayload | undefined) => {
      if (!old) return old;

      const updated = old.alerts.map(alert =>
        alert.id === alertId
          ? { ...alert, status: newStatus as Alert['status'] }
          : alert
      );

      if (feDebug()) console.log('[useAlerts] Updated alert status via WebSocket:', { alertId, newStatus });

      return {
        ...old,
        alerts: updated,
      };
    });
  };

  // Update stacked count for an existing alert row.
  const updateAlertStack = (alertId: string, count: unknown, lastSeen?: string) => {
    let didUpdate = false;
    const parsedCount = Number(count);
    const normalizedCount = Number.isFinite(parsedCount)
      ? Math.max(1, Math.trunc(parsedCount))
      : 1;

    queryClient.setQueryData(alertsQueryKey, (old: AlertsPayload | undefined) => {
      if (!old) return old;

      const updated = old.alerts.map((alert) => {
        if (alert.id !== alertId) return alert;
        didUpdate = true;
        return {
          ...alert,
          count: normalizedCount,
          last_seen: lastSeen || alert.last_seen,
          updated_at: lastSeen || alert.updated_at,
        };
      });

      if (!didUpdate) return old;
      return {
        ...old,
        alerts: updated,
      };
    });

    return didUpdate;
  };

  // WebSocket subscription for real-time alert state changes and reconnect handling
  useEffect(() => {
    let previousConnected = globalWebSocket.isConnected();
    const unsubscribeConnection = globalWebSocket.onConnectionChange((isConnected) => {
      setWsConnected(isConnected);
      // Refetch on reconnection (false -> true) to catch missed events
      if (isConnected && !previousConnected) {
        if (feDebug()) console.log('[useAlerts] WebSocket reconnected — refetching alerts');
        queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_PREFIX });
      }
      previousConnected = isConnected;
    });

    const unsubscribeFired = globalWebSocket.on('alert:fired', (message) => {
      const data = message?.data;
      if (data?.alert_id) {
        if (feDebug()) console.log('[useAlerts] Received alert:fired via WebSocket:', data);
        queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_PREFIX });
      }
    });

    const unsubscribeStacked = globalWebSocket.on('alert:stacked', (message) => {
      const data = message?.data;
      if (!data?.alert_id) return;

      if (feDebug()) console.log('[useAlerts] Received alert:stacked via WebSocket:', data);
      const updated = updateAlertStack(data.alert_id, data.count, data.last_seen);
      if (!updated) {
        // If this tab missed the original fired event, fetch canonical state.
        queryClient.invalidateQueries({ queryKey: ALERTS_QUERY_KEY_PREFIX });
      }
    });

    // Subscribe to alert state change events from the shared alert WebSocket relay.
    const unsubscribeStateChange = globalWebSocket.on('alert:state_changed', (message) => {
      const data = message?.data;
      if (data && data.alert_id && data.status) {
        if (feDebug()) console.log('[useAlerts] Received alert:state_changed via WebSocket:', data);
        // State transition (acknowledged) - update cache directly.
        updateAlertStatus(data.alert_id, data.status);
      }
    });

    return () => {
      unsubscribeConnection();
      unsubscribeFired();
      unsubscribeStacked();
      unsubscribeStateChange();
    };
  }, [queryClient, limit]);

  const limited = alertsMeta.hasMore;
  const activeLimit = alertsMeta.limit ?? alertsMeta.requestedLimit ?? null;

  return {
    alerts,
    alertsMeta,
    loading: isLoading,
    error: error?.message ?? null,
    fetchAlerts: refetch,
    updateAlerts,
    addAlert,
    limited,
    limit: activeLimit,
    acknowledgeAlert: (alertId: string, comment?: string) =>
      acknowledgeMutation.mutateAsync({ alertId, comment }),
    isAcknowledging: acknowledgeMutation.isPending,
  };
}

export function useContainers() {
  const queryClient = useQueryClient();
  const [wsConnected, setWsConnected] = useState(false);

  // Main query for fetching containers with caching
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: CONTAINERS_QUERY_KEY,
    queryFn: async () => {
      const response = await apiService.getContainers();
      return {
        containers: normalizeContainers(response.containers),
        groups: (response.groups || []).map(normalizeGroup),
      };
    },
    staleTime: 60 * 1000, // Containers change less frequently
    gcTime: 5 * 60 * 1000, // Keep in cache for 5 minutes
    refetchOnMount: 'always', // Always refetch on navigation — monitoring state may have changed while unmounted
  });

  // WebSocket effect for real-time updates
  useEffect(() => {
    let previousConnected = globalWebSocket.isConnected();
    const unsubscribeConnection = globalWebSocket.onConnectionChange((isConnected) => {
      setWsConnected(isConnected);
      // Refetch on reconnection (false -> true) to catch missed events
      if (isConnected && !previousConnected) {
        if (feDebug()) console.log('[useContainers] WebSocket reconnected — refetching containers');
        queryClient.invalidateQueries({ queryKey: CONTAINERS_QUERY_KEY });
      }
      previousConnected = isConnected;
    });

    const unsubscribeInventory = globalWebSocket.on('containers:inventory_update', (message) => {
      // Use data directly from WebSocket message to prevent HTTP feedback loop
      if (feDebug()) console.log('[useContainers] Received inventory_update via WebSocket:', message);
      const wsData = message && message.data;
      if (wsData) {
        if (wsData.containers !== undefined) {
          if (feDebug()) console.log('[useContainers] Updating containers from inventory payload');
          queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => ({
            containers: normalizeContainers(wsData.containers),
            groups: wsData.groups
              ? (Array.isArray(wsData.groups) ? wsData.groups : Object.values(wsData.groups || {})).map(normalizeGroup)
              : old?.groups ?? [],
          }));
        } else {
          if (feDebug()) console.log('[useContainers] Updating containers from inventory map payload');
          queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => ({
            containers: normalizeContainers(wsData),
            groups: old?.groups ?? [],
          }));
        }
      } else {
        if (feDebug()) console.warn('[useContainers] inventory_update missing data, falling back to HTTP');
        queryClient.invalidateQueries({ queryKey: CONTAINERS_QUERY_KEY });
      }
    });

    const unsubscribeContainerEvent = globalWebSocket.on('containers:event', (message) => {
      const wsData = message?.data;
      if (!wsData) return;
      const containerKey = typeof wsData.container_key === 'string' ? wsData.container_key : '';
      const status = typeof wsData.status === 'string' ? wsData.status : undefined;
      if (!containerKey || !status) return;
      queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => {
        if (!old) return old;
        return {
          ...old,
          containers: old.containers.map((container) =>
            container.container_key === containerKey
              ? { ...container, status }
              : container
          ),
        };
      });
    });

    const unsubscribeMonitoring = globalWebSocket.on('containers:monitoring_state_changed', (message) => {
      const wsData = message?.data;
      if (!wsData) return;
      const containerKey = typeof wsData.container_key === 'string' ? wsData.container_key : '';
      const monitoringEnabled = Boolean(wsData.monitoring_enabled);
      if (!containerKey) return;
      if (feDebug()) console.log('[useContainers] monitoring_state_changed:', { containerKey, monitoringEnabled });

      queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => {
        if (!old) return old;
        return {
          ...old,
          containers: old.containers.map((container) =>
            container.container_key === containerKey
              ? { ...container, monitoring_enabled: monitoringEnabled } as typeof container
              : container
          ),
        };
      });
    });

    // Subscribe to group events
    const unsubscribeGroupCreated = globalWebSocket.on('group_created', (msg: any) => {
      const raw = msg?.data;
      if (raw) {
        const group = normalizeGroup(raw);
        queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => {
          if (!old) return old;
          const without = old.groups.filter(g => g.groupId !== group.groupId);
          return { ...old, groups: [...without, group] };
        });
      }
    });

    const unsubscribeGroupUpdated = globalWebSocket.on('group_updated', (msg: any) => {
      const raw = msg?.data;
      if (raw) {
        const updatedGroup = normalizeGroup(raw);
        queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => {
          if (!old) return old;
          return {
            ...old,
            groups: old.groups.map(group =>
              group.groupId === updatedGroup.groupId ? updatedGroup : group
            ),
          };
        });
      }
    });

    const unsubscribeGroupDeleted = globalWebSocket.on('group_deleted', (msg: any) => {
      const deletedGroup: { groupId: number } = msg?.data;
      if (deletedGroup) {
        queryClient.setQueryData(CONTAINERS_QUERY_KEY, (old: typeof data) => {
          if (!old) return old;
          return {
            ...old,
            groups: old.groups.filter(group => group.groupId !== deletedGroup.groupId),
          };
        });
      }
    });

    return () => {
      unsubscribeConnection();
      unsubscribeInventory();
      unsubscribeContainerEvent();
      unsubscribeMonitoring();
      unsubscribeGroupCreated();
      unsubscribeGroupUpdated();
      unsubscribeGroupDeleted();
    };
  }, [queryClient]);

  return {
    containers: data?.containers ?? [],
    groups: data?.groups ?? [],
    loading: isLoading,
    error: error?.message ?? null,
    fetchContainers: refetch,
    wsConnected,
  };
}

export function useHealth() {
  const { data, isLoading, refetch } = useQuery({
    queryKey: HEALTH_QUERY_KEY,
    queryFn: () => apiService.getHealth(),
    staleTime: 30 * 1000, // Consider data stale after 30s
    gcTime: 60 * 1000, // Keep in cache for 1 minute
    refetchInterval: 30000, // Auto-refresh every 30s
  });

  return {
    health: data ?? null,
    loading: isLoading,
    fetchHealth: refetch,
  };
}

// Dedicated hook for WebSocket alert handling - should only be used once in App.tsx
export function useWebSocketAlerts(addAlert: (alert: Alert) => void) {
  useEffect(() => {
    const unsubscribeAlerts = globalWebSocket.on('alert_triggered', (msg: any) => {
      const alert: Alert = msg?.data;
      if (alert) {
        console.log('[WebSocketAlerts] New alert received via WebSocket:', alert);
        addAlert(alert);
      }
    });

    return () => {
      unsubscribeAlerts();
    };
  }, [addAlert]);
}
