/**
 * AlertHistoryPanel Component
 *
 * Displays past alert events with filtering and pagination.
 * Extracted from routes/alerting/history.tsx for embedding as a sub-tab
 * within the Stats page.
 */

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Clock, AlertCircle, ChevronLeft, ChevronRight, Loader2 } from 'lucide-react';
import Card from '~/features/alert-engine/components/ui/Card';
import { apiService } from '~/features/alert-engine/services/api';
import { formatLocalDateTime } from '~/features/alert-engine/utils/date';
import type { AlertHistoryItem } from '~/features/alert-engine/types';
import { getSeverityBadgeClasses, getStatusBadgeClasses } from '~/utils/theme';

type TimeRange = 'hour' | '24h' | '7d' | '30d';
type AlertStatus = 'triggered' | 'acknowledged' | 'silenced';

interface AlertHistoryPanelProps {
  initialRuleId?: string;
  initialStatus?: string;
}

// Status badge component
const StatusBadge: React.FC<{ status: string }> = ({ status }) => {
  const normalizedStatus = status.toLowerCase();
  const statusLabels: Record<string, string> = {
    triggered: "Triggered",
    firing: "Triggered",
    acknowledged: "Acknowledged",
    silenced: "Silenced",
  };

  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${getStatusBadgeClasses(normalizedStatus)}`}>
      {statusLabels[normalizedStatus] || statusLabels.firing}
    </span>
  );
};

// Severity badge component
const SeverityBadge: React.FC<{ severity: string }> = ({ severity }) => {
  return (
    <span className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${getSeverityBadgeClasses(severity)}`}>
      {severity}
    </span>
  );
};

// Convert time range to ISO timestamps
function getTimeRangeTimestamps(range: TimeRange): { start_time: string; end_time: string } {
  const end = new Date();
  const start = new Date();

  switch (range) {
    case 'hour':
      start.setHours(start.getHours() - 1);
      break;
    case '24h':
      start.setHours(start.getHours() - 24);
      break;
    case '7d':
      start.setDate(start.getDate() - 7);
      break;
    case '30d':
      start.setDate(start.getDate() - 30);
      break;
  }

  return {
    start_time: start.toISOString(),
    end_time: end.toISOString(),
  };
}

export default function AlertHistoryPanel({ initialRuleId, initialStatus }: AlertHistoryPanelProps) {
  const [timeRange, setTimeRange] = useState<TimeRange>('24h');
  const [severity, setSeverity] = useState<string>('');
  const normalizeStatus = (value?: string) => (value === 'firing' ? 'triggered' : (value || ''));
  const [status, setStatus] = useState<string>(normalizeStatus(initialStatus));
  const [page, setPage] = useState(0);
  const pageSize = 50;

  // Calculate time range for API
  const { start_time, end_time } = getTimeRangeTimestamps(timeRange);

  // Fetch alert history
  const { data, isLoading, error } = useQuery({
    queryKey: ['alert-history', timeRange, severity, status, page, initialRuleId],
    queryFn: async () => {
      const params: any = {
        start_time,
        end_time,
        offset: page * pageSize,
        limit: pageSize,
      };

      if (severity) params.severity = severity;
      if (status) params.status = normalizeStatus(status);
      if (initialRuleId) params.rule_id = initialRuleId;

      return apiService.getAlertHistory(params);
    },
  });

  const items = data?.items || [];
  const total = data?.total || 0;
  const hasNextPage = (page + 1) * pageSize < total;
  const hasPrevPage = page > 0;

  // Reset to page 0 when filters change
  const handleFilterChange = (filterSetter: (value: any) => void, value: any) => {
    setPage(0);
    filterSetter(value);
  };

  const timeRangeButtons = [
    { value: 'hour' as TimeRange, label: 'Last Hour' },
    { value: '24h' as TimeRange, label: 'Last 24 Hours' },
    { value: '7d' as TimeRange, label: 'Last 7 Days' },
    { value: '30d' as TimeRange, label: 'Last 30 Days' },
  ];

  const severityOptions = [
    { value: '', label: 'All Severities' },
    { value: 'critical', label: 'Critical' },
    { value: 'warning', label: 'Warning' },
    { value: 'info', label: 'Info' },
  ];

  const statusOptions = [
    { value: '', label: 'All Statuses' },
    { value: 'triggered', label: 'Triggered' },
    { value: 'acknowledged', label: 'Acknowledged' },
    { value: 'silenced', label: 'Silenced' },
  ];

  return (
    <div>
      {/* Filters Card */}
      <Card className="mb-6">
        <div className="p-4">
          <div className="space-y-4">
            {/* Time Range Buttons */}
            <div>
              <label className="mb-2 block text-sm font-medium text-text">
                Time Range
              </label>
              <div className="flex flex-wrap gap-2">
                {timeRangeButtons.map((btn) => (
                  <button
                    key={btn.value}
                    onClick={() => handleFilterChange(setTimeRange, btn.value)}
                    className={`px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                      timeRange === btn.value
                        ? 'bg-primary text-primary-50'
                        : 'bg-foreground/10 text-text hover:bg-foreground/20'
                    }`}
                  >
                    {btn.label}
                  </button>
                ))}
              </div>
            </div>

            {/* Severity and Status Filters */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Severity Filter */}
              <div>
                <label className="mb-2 block text-sm font-medium text-text">
                  Severity
                </label>
                <select
                  value={severity}
                  onChange={(e) => handleFilterChange(setSeverity, e.target.value)}
                  className="w-full rounded-lg border border-divider bg-background px-3 py-2 text-text focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  {severityOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              {/* Status Filter */}
              <div>
                <label className="mb-2 block text-sm font-medium text-text">
                  Status
                </label>
                <select
                  value={status}
                  onChange={(e) => handleFilterChange(setStatus, e.target.value)}
                  className="w-full rounded-lg border border-divider bg-background px-3 py-2 text-text focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/30"
                >
                  {statusOptions.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </div>
      </Card>

      {/* History Table Card */}
      <Card className="overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <Loader2 className="mx-auto mb-4 h-8 w-8 animate-spin text-primary" />
              <p className="text-neutral">Loading alert history...</p>
            </div>
          </div>
        ) : error ? (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <AlertCircle className="mx-auto mb-4 h-12 w-12 text-error" />
              <p className="text-error">
                {error instanceof Error ? error.message : 'Failed to load alert history'}
              </p>
            </div>
          </div>
        ) : items.length === 0 ? (
          <div className="flex items-center justify-center py-16">
            <div className="text-center">
              <Clock className="mx-auto mb-4 h-12 w-12 text-neutral/60" />
              <p className="text-neutral">No alert history found</p>
              <p className="mt-2 text-sm text-neutral/80">
                Try adjusting your filters or time range
              </p>
            </div>
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="min-w-full">
                <thead>
                  <tr className="border-b border-divider bg-foreground/10">
                    <th className="px-6 py-4 text-left text-xs font-bold uppercase tracking-wider text-neutral">
                      Time
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-bold uppercase tracking-wider text-neutral">
                      Rule
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-bold uppercase tracking-wider text-neutral">
                      Severity
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-bold uppercase tracking-wider text-neutral">
                      Status
                    </th>
                    <th className="px-6 py-4 text-left text-xs font-bold uppercase tracking-wider text-neutral">
                      Message
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-divider/60">
                  {items.map((item: AlertHistoryItem, index: number) => (
                    <tr
                      key={item.id}
                      className="animate-fade-in transition-colors duration-200 hover:bg-foreground/10"
                      style={{ animationDelay: `${index * 30}ms` }}
                    >
                      <td className="whitespace-nowrap px-6 py-4 font-mono text-sm text-neutral">
                        {formatLocalDateTime(item.triggered_at)}
                      </td>
                      <td className="px-6 py-4">
                        <div className="text-sm font-medium text-text">
                          {item.rule_name}
                        </div>
                      </td>
                      <td className="px-6 py-4">
                        <SeverityBadge severity={item.severity} />
                      </td>
                      <td className="px-6 py-4">
                        <StatusBadge status={item.status} />
                      </td>
                      <td className="px-6 py-4">
                        <div className="max-w-md truncate text-sm text-text">
                          {item.message}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Pagination */}
            <div className="border-t border-divider bg-foreground/10 px-6 py-4">
              <div className="flex items-center justify-between">
                <div className="text-sm text-neutral">
                  Showing {page * pageSize + 1}-{Math.min((page + 1) * pageSize, total)} of {total} results
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => setPage(page - 1)}
                    disabled={!hasPrevPage}
                    className="inline-flex items-center rounded-lg border border-divider bg-background px-3 py-2 text-sm font-medium text-text transition-colors hover:bg-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    <ChevronLeft className="w-4 h-4 mr-1" />
                    Previous
                  </button>
                  <button
                    onClick={() => setPage(page + 1)}
                    disabled={!hasNextPage}
                    className="inline-flex items-center rounded-lg border border-divider bg-background px-3 py-2 text-sm font-medium text-text transition-colors hover:bg-foreground/10 disabled:cursor-not-allowed disabled:opacity-50"
                  >
                    Next
                    <ChevronRight className="w-4 h-4 ml-1" />
                  </button>
                </div>
              </div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
