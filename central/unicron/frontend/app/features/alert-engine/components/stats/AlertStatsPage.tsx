/**
 * AlertStatsPage - Alert statistics with charts and KPIs
 *
 * Ported from LogForge alert-engine/frontend/pages/AlertStatsPage.tsx
 * Provides alert analytics with visual charts showing alert distribution and trends over time.
 */

import React, { useMemo, useState, useEffect, useRef, useCallback } from 'react';
import {
  PieChart,
  Pie,
  Cell,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Brush,
} from 'recharts';
import {
  Calendar,
  Clock,
  TrendingUp,
  BarChart3,
  Filter,
  X,
  Eye,
  EyeOff,
  HelpCircle,
} from 'lucide-react';
import type { Alert, AlertsMeta } from '../../types';
import { Card, Button } from '../ui';
import { getChartSeriesColor, getChartSurfaceColors, themeColorVar } from '~/utils/theme';

interface AlertStatsPageProps {
  alerts: Alert[];
  onFilterChange: (filters: AlertFilters) => void;
  currentFilters: AlertFilters;
  meta?: AlertsMeta;
  onRefreshRef?: React.MutableRefObject<(() => void) | null>;
}

export interface AlertFilters {
  ruleIds?: string[];
  containerIds?: string[];
  timeRange?: {
    start: Date;
    end: Date;
  };
}

interface TimeRange {
  label: string;
  hours: number;
}

const timeRanges: TimeRange[] = [
  { label: 'Last Hour', hours: 1 },
  { label: 'Last 24 Hours', hours: 24 },
  { label: 'Last 7 Days', hours: 24 * 7 },
  { label: 'Last 30 Days', hours: 24 * 30 },
];

// Sample data for empty pie chart
const SAMPLE_PIE_DATA = [
  { name: 'Sample - High CPU', count: 12, id: 'sample-cpu' },
  { name: 'Sample - Memory Alert', count: 8, id: 'sample-memory' },
  { name: 'Sample - Container Down', count: 5, id: 'sample-container' },
  { name: 'Sample - Log Error', count: 15, id: 'sample-logs' },
];

// Sample data localStorage key
const SAMPLE_DATA_KEY = 'alertStats_hideSampleData';

// Responsive breakpoints with chart width measurement
const useResponsiveBreakpoint = () => {
  const [breakpoint, setBreakpoint] = useState<'mobile' | 'tablet' | 'desktop'>('desktop');

  useEffect(() => {
    const updateBreakpoint = () => {
      const width = window.innerWidth;
      if (width < 768) setBreakpoint('mobile');
      else if (width < 1024) setBreakpoint('tablet');
      else setBreakpoint('desktop');
    };

    updateBreakpoint();
    window.addEventListener('resize', updateBreakpoint);
    return () => window.removeEventListener('resize', updateBreakpoint);
  }, []);

  return breakpoint;
};

// Chart container measurement. Recharts warns when mounted inside hidden tab
// panels, so charts only render after the visible container has real bounds.
const useChartContainerSize = () => {
  const [chartSize, setChartSize] = useState({ width: 800, height: 0 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!containerRef.current || typeof ResizeObserver === 'undefined') return;

    const resizeObserver = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setChartSize({
          width,
          height,
        });
      }
    });

    resizeObserver.observe(containerRef.current);
    return () => resizeObserver.disconnect();
  }, []);

  return {
    chartWidth: chartSize.width > 0 ? chartSize.width : 800,
    chartHeight: chartSize.height > 0 ? chartSize.height : 300,
    isChartVisible: chartSize.width > 0 && chartSize.height > 0,
    containerRef,
  };
};

// Smart tick calculation for timeline
const calculateOptimalTicks = (
  rangeHours: number,
  bucketSizeMs: number,
  chartWidth: number,
  breakpoint: 'mobile' | 'tablet' | 'desktop'
) => {
  // Responsive tick budget
  const maxTicks = breakpoint === 'mobile' ? 5 : breakpoint === 'tablet' ? 7 : 10;

  // Calculate available ticks based on range and bucket size
  const totalBuckets = Math.ceil((rangeHours * 3600 * 1000) / bucketSizeMs);

  // Choose step size to stay within budget while maintaining bucket alignment
  let stepSize = 1;
  while (Math.ceil(totalBuckets / stepSize) > maxTicks) {
    // Increase step in logical increments based on bucket type
    if (bucketSizeMs === 60 * 60 * 1000) {
      // Hourly buckets
      const hourlySteps = [1, 2, 3, 6, 12, 24];
      const currentHours = stepSize;
      const nextStep = hourlySteps.find((h) => h > currentHours) || currentHours * 2;
      stepSize = nextStep;
    } else if (bucketSizeMs === 3 * 60 * 60 * 1000) {
      // 3-hour buckets
      stepSize = stepSize < 2 ? 2 : stepSize * 2; // 6h, 12h, 24h
    } else if (bucketSizeMs === 24 * 60 * 60 * 1000) {
      // Daily buckets
      const dailySteps = [1, 2, 3, 7, 14];
      const currentDays = stepSize;
      const nextStep = dailySteps.find((d) => d > currentDays) || currentDays * 2;
      stepSize = nextStep;
    } else {
      // Weekly buckets
      stepSize = stepSize * 2; // 2 weeks, 4 weeks, etc.
    }
  }

  // Determine if rotation is needed after density reduction
  const estimatedTickWidth = 80; // Approximate width per tick label
  const availableWidth = chartWidth * 0.8; // Account for margins
  const tickCount = Math.ceil(totalBuckets / stepSize);
  const needsRotation = tickCount * estimatedTickWidth > availableWidth;

  const rotation = needsRotation
    ? breakpoint === 'mobile'
      ? -30
      : breakpoint === 'tablet'
        ? -20
        : -15
    : 0;

  return { stepSize, tickCount, rotation };
};

// Format tick labels based on range type
const formatTickLabel = (timestamp: number, rangeHours: number) => {
  const date = new Date(timestamp);

  if (rangeHours <= 24) {
    // <=24h: time only (11PM, 12AM)
    return date.toLocaleString(undefined, { hour: 'numeric' });
  } else if (rangeHours <= 24 * 7) {
    // 1d-7d: date + hour for 12-hour major ticks (08/08 6AM, 08/08 6PM)
    return date.toLocaleString(undefined, { month: '2-digit', day: '2-digit', hour: 'numeric' });
  } else {
    // >7d: date only (08/08)
    return date.toLocaleString(undefined, { month: '2-digit', day: '2-digit' });
  }
};

export const AlertStatsPage: React.FC<AlertStatsPageProps> = ({
  alerts,
  onFilterChange,
  currentFilters,
  meta,
  onRefreshRef,
}) => {
  const breakpoint = useResponsiveBreakpoint();
  const {
    chartWidth,
    chartHeight: timelineChartHeight,
    containerRef: timelineContainerRef,
    isChartVisible: isTimelineChartVisible,
  } = useChartContainerSize();
  const {
    chartWidth: pieChartWidth,
    chartHeight: pieChartHeight,
    containerRef: pieContainerRef,
    isChartVisible: isPieChartVisible,
  } = useChartContainerSize();
  const [selectedTimeRange, setSelectedTimeRange] = useState<TimeRange>(timeRanges[1]); // 24 hours default
  const [customRange, setCustomRange] = useState<{ start: string; end: string }>({
    start: '',
    end: '',
  });
  const [isCustomRange, setIsCustomRange] = useState(false);
  const [hideSampleData, setHideSampleData] = useState(() => {
    try {
      return localStorage.getItem(SAMPLE_DATA_KEY) === 'true';
    } catch {
      return false;
    }
  });

  // Snapshot state: freeze stats for stable analysis
  // Initialize as null - wait for real data before creating snapshot
  const [statsSnapshot, setStatsSnapshot] = useState<{
    alerts: Alert[];
    meta: AlertsMeta;
    snapshotTimestamp: Date; // When snapshot was captured (for UX/display)
    latestAlertTimestamp: Date; // Newest alert timestamp (for filtering)
  } | null>(null);

  // Track user interaction to pause auto-refresh
  const [isPaused, setIsPaused] = useState(false);

  // Helper to create snapshot with dual timestamps
  const createSnapshot = (alertsArray: Alert[], metaData: AlertsMeta) => {
    const snapshotTimestamp = new Date();
    const latestAlertTimestamp =
      alertsArray.length > 0
        ? new Date(Math.max(...alertsArray.map((a) => new Date(a.timestamp).getTime())))
        : snapshotTimestamp;

    return {
      alerts: [...alertsArray],
      meta: metaData,
      snapshotTimestamp,
      latestAlertTimestamp,
    };
  };

  // Initialize snapshot when real data arrives
  useEffect(() => {
    if (meta && alerts.length > 0 && !statsSnapshot) {
      setStatsSnapshot(createSnapshot(alerts, meta));
    }
  }, [meta, alerts, statsSnapshot]);

  const limitValue = statsSnapshot?.meta?.limit ?? statsSnapshot?.meta?.requestedLimit ?? 100;
  const limitedToRecent = Boolean(statsSnapshot?.meta?.hasMore);

  // Detect new alerts by comparing ID sets (handles trimming correctly)
  const newAlertInfo = useMemo(() => {
    if (!statsSnapshot) {
      return { count: 0, hasNewer: false, isAtLimit: false };
    }

    const snapshotIds = new Set(statsSnapshot.alerts.map((a) => a.id));
    const newAlerts = alerts.filter((a) => !snapshotIds.has(a.id));

    // Get newest timestamp from live alerts
    const newestLiveTimestamp = alerts.length > 0 ? new Date(alerts[0].timestamp).getTime() : 0;
    const newestSnapshotTimestamp =
      statsSnapshot.alerts.length > 0
        ? new Date(statsSnapshot.alerts[0].timestamp).getTime()
        : 0;

    return {
      count: newAlerts.length,
      hasNewer: newestLiveTimestamp > newestSnapshotTimestamp,
      isAtLimit: alerts.length >= limitValue && meta?.hasMore,
    };
  }, [alerts, statsSnapshot, limitValue, meta?.hasMore]);

  // Manual refresh handler (wrapped in useCallback for stable reference)
  const handleRefreshStats = useCallback(() => {
    if (!meta) return;
    setStatsSnapshot(createSnapshot(alerts, meta));
    setIsPaused(false); // Resume auto-refresh after manual refresh
  }, [alerts, meta]);

  // Expose refresh function to parent via ref for WebSocket updates
  useEffect(() => {
    if (onRefreshRef) {
      onRefreshRef.current = handleRefreshStats;
    }
    return () => {
      if (onRefreshRef) {
        onRefreshRef.current = null;
      }
    };
  }, [handleRefreshStats, onRefreshRef]);

  // Auto-refresh: update snapshot when not paused and no user interaction (fallback for WebSocket)
  useEffect(() => {
    if (isPaused) return;

    // Auto-refresh every 30 seconds if no user interaction (fallback when WebSocket disconnects)
    const interval = setInterval(() => {
      if (!isPaused) {
        handleRefreshStats();
      }
    }, 30000);

    return () => clearInterval(interval);
  }, [isPaused, handleRefreshStats]);

  // Pause auto-refresh when user interacts with filters or time range
  useEffect(() => {
    setIsPaused(true);
  }, [currentFilters, selectedTimeRange, isCustomRange, customRange]);

  // Calculate time range (stable - no live data dependency)
  const timeRange = useMemo(() => {
    if (isCustomRange && customRange.start && customRange.end) {
      return {
        start: new Date(customRange.start),
        end: new Date(customRange.end),
      };
    }

    if (!statsSnapshot) {
      // Fallback to current time if no snapshot yet
      const end = new Date();
      const start = new Date(end.getTime() - selectedTimeRange.hours * 60 * 60 * 1000);
      return { start, end };
    }

    // Use latestAlertTimestamp to ensure all snapshot alerts pass the filter
    // Falls back to snapshotTimestamp if no alerts (empty snapshot guard)
    const end = statsSnapshot.latestAlertTimestamp;
    const start = new Date(end.getTime() - selectedTimeRange.hours * 60 * 60 * 1000);
    return { start, end };
  }, [selectedTimeRange, customRange, isCustomRange, statsSnapshot]);

  // Filter alerts by time range and current filters (uses snapshot for stable stats)
  const filteredAlerts = useMemo(() => {
    if (!statsSnapshot) return [];

    return statsSnapshot.alerts.filter((alert) => {
      const alertTime = new Date(alert.timestamp);
      const inTimeRange = alertTime >= timeRange.start && alertTime <= timeRange.end;

      if (!inTimeRange) return false;

      if (currentFilters.ruleIds?.length && !currentFilters.ruleIds.includes(alert.rule_id)) {
        return false;
      }

      if (currentFilters.containerIds?.length) {
        const containerId = alert.context?.container_identifier;
        if (!containerId || !currentFilters.containerIds.includes(containerId)) {
          return false;
        }
      }

      return true;
    });
  }, [statsSnapshot, timeRange, currentFilters]);

  // Calculate KPIs (uses snapshot for stable stats)
  const kpis = useMemo(() => {
    if (!statsSnapshot) {
      return {
        totalAlertsDisplay: '0',
        currentAlertsPerHour: 0,
        averageAlertsPerHour: 0,
      };
    }

    const filteredCount = filteredAlerts.length;
    const hoursInRange = (timeRange.end.getTime() - timeRange.start.getTime()) / (1000 * 60 * 60);
    const currentAlertsPerHour = hoursInRange > 0 ? filteredCount / hoursInRange : filteredCount;

    const oldestLoadedTimestamp =
      statsSnapshot.alerts.length > 0
        ? statsSnapshot.alerts[statsSnapshot.alerts.length - 1].timestamp
        : null;
    const hoursSinceOldest = oldestLoadedTimestamp
      ? (statsSnapshot.snapshotTimestamp.getTime() - new Date(oldestLoadedTimestamp).getTime()) /
        (1000 * 60 * 60)
      : 1;
    const averageAlertsPerHour =
      hoursSinceOldest > 0 ? statsSnapshot.alerts.length / hoursSinceOldest : statsSnapshot.alerts.length;

    const cappedDisplay =
      limitedToRecent && limitValue != null && filteredCount >= (limitValue ?? filteredCount);
    const totalAlertsDisplay = cappedDisplay ? `${limitValue}+` : filteredCount.toString();

    return {
      totalAlertsDisplay,
      currentAlertsPerHour: Number(currentAlertsPerHour.toFixed(1)),
      averageAlertsPerHour: Number(averageAlertsPerHour.toFixed(1)),
    };
  }, [filteredAlerts, statsSnapshot, limitedToRecent, limitValue, timeRange]);

  // Prepare pie chart data (alerts by rule)
  const { pieData, hasRealData, totalPie } = useMemo(() => {
    const ruleCount = new Map<string, { name: string; count: number; id: string }>();

    filteredAlerts.forEach((alert) => {
      const key = alert.rule_id;
      if (ruleCount.has(key)) {
        ruleCount.get(key)!.count++;
      } else {
        ruleCount.set(key, {
          name: alert.rule_name,
          count: 1,
          id: alert.rule_id,
        });
      }
    });

    let data = Array.from(ruleCount.values()).sort((a, b) => b.count - a.count);
    const hasRealData = data.length > 0;

    // Keep top 5, group rest as "Other"
    if (data.length > 5) {
      const top5 = data.slice(0, 5);
      const others = data.slice(5);
      const otherCount = others.reduce((sum, item) => sum + item.count, 0);

      if (otherCount > 0) {
        top5.push({
          name: 'Other',
          count: otherCount,
          id: 'other',
        });
      }
      data = top5;
    }

    // Show sample data if no real data and user hasn't hidden it
    if (!hasRealData && !hideSampleData) {
      data = SAMPLE_PIE_DATA;
    }
    // Compute total for legend/center
    const totalPie = data.reduce((sum, d) => sum + d.count, 0);
    return { pieData: data, hasRealData, totalPie };
  }, [filteredAlerts, hideSampleData]);

  // Prepare timeline data with smart tick calculation and bucket alignment
  const { timelineData, tickConfig } = useMemo(() => {
    const rangeHours = (timeRange.end.getTime() - timeRange.start.getTime()) / (1000 * 60 * 60);

    // Adaptive binning
    let bucketSizeMs: number;

    if (rangeHours <= 24) {
      bucketSizeMs = 60 * 60 * 1000; // 1 hour
    } else if (rangeHours <= 24 * 14) {
      bucketSizeMs = 3 * 60 * 60 * 1000; // 3 hours
    } else if (rangeHours <= 24 * 60) {
      bucketSizeMs = 24 * 60 * 60 * 1000; // 1 day
    } else {
      bucketSizeMs = 7 * 24 * 60 * 60 * 1000; // 1 week
    }

    // Calculate optimal tick configuration
    const tickConfig = calculateOptimalTicks(rangeHours, bucketSizeMs, chartWidth, breakpoint);

    const buckets = new Map<number, number>();

    // Initialize buckets - start from bucket-aligned timestamp
    const startBucket = Math.floor(timeRange.start.getTime() / bucketSizeMs) * bucketSizeMs;
    const endTime = timeRange.end.getTime();

    let currentTime = startBucket;
    while (currentTime <= endTime) {
      buckets.set(currentTime, 0);
      currentTime += bucketSizeMs;
    }

    // Fill buckets with alert counts
    filteredAlerts.forEach((alert) => {
      const alertTime = new Date(alert.timestamp).getTime();
      const bucketKey = Math.floor(alertTime / bucketSizeMs) * bucketSizeMs;
      buckets.set(bucketKey, (buckets.get(bucketKey) || 0) + 1);
    });

    // Create timeline data with bucket-aligned ticks
    const allData = Array.from(buckets.entries())
      .sort(([a], [b]) => a - b)
      .map(([timestamp, count]) => ({
        time: formatTickLabel(timestamp, rangeHours),
        alerts: count,
        timestamp,
        fullTimestamp: new Date(timestamp).toLocaleString(), // For tooltips
        isTickMark: false, // Will be set for actual tick positions
      }));

    // Mark which entries should be tick marks based on step size
    allData.forEach((entry, index) => {
      entry.isTickMark = index % tickConfig.stepSize === 0;
    });

    return {
      timelineData: allData,
      tickConfig,
    };
  }, [filteredAlerts, timeRange, breakpoint, chartWidth]);

  const handleTimeRangeChange = (range: TimeRange) => {
    setSelectedTimeRange(range);
    setIsCustomRange(false);
  };

  const handleCustomRangeSubmit = () => {
    if (customRange.start && customRange.end) {
      setIsCustomRange(true);
    }
  };

  const handlePieClick = (data: { id: string; name: string; count: number }) => {
    if (data.id === 'other' || data.id.startsWith('sample-')) return;

    onFilterChange({
      ...currentFilters,
      ruleIds: [data.id],
    });
  };

  const clearFilters = () => {
    onFilterChange({});
  };

  const toggleSampleData = () => {
    const newValue = !hideSampleData;
    setHideSampleData(newValue);
    try {
      localStorage.setItem(SAMPLE_DATA_KEY, String(newValue));
    } catch (error) {
      console.warn('Failed to save sample data preference:', error);
    }
  };

  const hasFilters = currentFilters.ruleIds?.length || currentFilters.containerIds?.length;
  const hasTimelineData = timelineData.some((d) => d.alerts > 0);
  const showNoDataBanner = !hasRealData && !hasTimelineData;
  const chartSurfaceColors = getChartSurfaceColors();
  const neutralChartColor = chartSurfaceColors.muted;
  const timelineColor = themeColorVar("chart-1");

  // Pie interactions
  const [activeSlice, setActiveSlice] = useState<number | null>(null);
  const handleSliceEnter = (_: unknown, index: number) => setActiveSlice(index);
  const handleSliceLeave = () => setActiveSlice(null);

  // Slice label for larger segments only
  const renderSliceLabel = (props: { value?: number }) => {
    if (!totalPie || !props.value) return '';
    const pct = (props.value / totalPie) * 100;
    return pct >= 8 ? `${Math.round(pct)}%` : '';
  };

  return (
    <div className="space-y-6">
      {/* Time Selector Row */}
      <Card className="p-6">
        <div className="flex flex-wrap items-center gap-4">
          <div className="flex items-center space-x-2">
            <Calendar className="w-5 h-5 text-neutral" />
            <span className="font-medium text-text">Time Range:</span>
          </div>

          {timeRanges.map((range) => (
            <Button
              key={range.label}
              variant={selectedTimeRange === range && !isCustomRange ? 'primary' : 'secondary'}
              size="sm"
              onClick={() => handleTimeRangeChange(range)}
            >
              {range.label}
            </Button>
          ))}

          <div className="flex items-center space-x-2">
            <input
              type="datetime-local"
              value={customRange.start}
              onChange={(e) => setCustomRange((prev) => ({ ...prev, start: e.target.value }))}
              className="rounded border border-divider bg-background px-3 py-1 text-sm text-text"
              step="60"
            />
            <span className="text-neutral">to</span>
            <input
              type="datetime-local"
              value={customRange.end}
              onChange={(e) => setCustomRange((prev) => ({ ...prev, end: e.target.value }))}
              className="rounded border border-divider bg-background px-3 py-1 text-sm text-text"
              step="60"
            />
            <Button
              size="sm"
              onClick={handleCustomRangeSubmit}
              disabled={!customRange.start || !customRange.end}
            >
              Apply
            </Button>
          </div>
        </div>
      </Card>

      {/* Stats Info Banner */}
      {(limitedToRecent || newAlertInfo.count > 0 || isPaused) && (
        <div className="flex items-center justify-between rounded border border-divider bg-foreground/5 px-3 py-2">
          <div className="flex items-center space-x-2">
            <TrendingUp className="w-4 h-4 text-neutral" />
            <div className="flex items-center gap-2 text-sm">
              {newAlertInfo.count > 0 ? (
                <span className="text-text">
                  {newAlertInfo.count >= 100 ? '99+' : newAlertInfo.count} new alert
                  {newAlertInfo.count > 1 ? 's' : ''} since last refresh
                </span>
              ) : isPaused ? (
                <span className="text-text">Auto-refresh paused</span>
              ) : null}
              {limitedToRecent && (newAlertInfo.count > 0 || isPaused) && (
                <span className="text-neutral">-</span>
              )}
              {limitedToRecent && (
                <span className="text-neutral">
                  Stats computed over last {limitValue ?? 100} loaded alerts
                </span>
              )}
            </div>
          </div>
          <button
            onClick={handleRefreshStats}
            className="rounded bg-foreground/10 px-2 py-1 text-xs text-text transition-colors hover:bg-foreground/20"
          >
            Refresh
          </button>
        </div>
      )}

      {/* No Data Banner */}
      {showNoDataBanner && (
        <div className="flex items-center justify-between rounded-lg border border-warning/30 bg-warning/15 px-4 py-3">
          <div className="flex items-center space-x-2">
            <BarChart3 className="w-5 h-5 text-warning" />
            <span className="text-sm font-medium text-warning">
              No data in selected range
            </span>
            <span className="text-sm text-warning">
              - Charts show sample data for preview
            </span>
          </div>
          {!hasRealData && !hideSampleData && (
            <button
              onClick={toggleSampleData}
              className="flex items-center space-x-1 rounded px-2 py-1 text-sm text-warning transition-colors hover:bg-warning/20"
            >
              <EyeOff className="w-4 h-4" />
              <span>Hide sample data</span>
            </button>
          )}
        </div>
      )}

      {/* Active Filters */}
      {hasFilters && (
        <div className="flex items-center justify-between rounded-lg border border-info/30 bg-info/15 px-4 py-2">
          <div className="flex items-center space-x-2">
            <Filter className="w-4 h-4 text-info" />
            <span className="text-sm font-medium text-info">
              Filters applied
            </span>
            {currentFilters.ruleIds?.length && (
              <span className="text-sm text-info">
                {currentFilters.ruleIds.length} rule{currentFilters.ruleIds.length > 1 ? 's' : ''}
              </span>
            )}
          </div>
          <button
            onClick={clearFilters}
            className="flex items-center space-x-1 text-sm text-info transition-colors hover:brightness-110"
          >
            <X className="w-4 h-4" />
            <span>Clear</span>
          </button>
        </div>
      )}

      {/* KPI Cards Row */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card className="p-6 relative">
          <span
            className="absolute top-3 right-3"
            title={`Total alerts in the selected range based on the loaded alert window`}
            aria-label="Help: Total Alerts"
          >
            <HelpCircle className="w-4 h-4 text-neutral" />
          </span>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral">Total Alerts</p>
              <p className="text-2xl font-bold text-text">
                {kpis.totalAlertsDisplay}
              </p>
            </div>
            <BarChart3 className="w-8 h-8 text-primary" />
          </div>
        </Card>

        <Card className="p-6 relative">
          <span
            className="absolute top-3 right-3"
            title={`Alerts per hour in the selected range based on loaded alerts`}
            aria-label="Help: Current Rate"
          >
            <HelpCircle className="w-4 h-4 text-neutral" />
          </span>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral">Current Rate</p>
              <p className="text-2xl font-bold text-text">
                {kpis.currentAlertsPerHour}/hr
              </p>
            </div>
            <TrendingUp className="w-8 h-8 text-success" />
          </div>
        </Card>

        <Card className="p-6 relative">
          <span
            className="absolute top-3 right-3"
            title={`Alerts per hour since the oldest loaded alert in the loaded set`}
            aria-label="Help: Average Rate"
          >
            <HelpCircle className="w-4 h-4 text-neutral" />
          </span>
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-neutral">Average Rate</p>
              <p className="text-2xl font-bold text-text">
                {kpis.averageAlertsPerHour}/hr
              </p>
            </div>
            <Clock className="w-8 h-8 text-warning" />
          </div>
        </Card>
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Pie Chart */}
        <Card className="p-6 relative">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-lg font-bold text-text">
              Alerts by Rule
            </h3>
            <div className="flex items-center gap-3">
              {hasFilters && (
                <div className="flex items-center gap-2 rounded-full border border-info/30 bg-info/15 px-2.5 py-1 text-xs text-info">
                  <span className="font-medium">Filter:</span>
                  <span className="truncate max-w-[12rem]">
                    {(() => {
                      const ids = currentFilters.ruleIds || [];
                      if (ids.length === 1) {
                        const match = pieData.find((p) => p.id === ids[0]);
                        return match?.name || 'Selected rule';
                      }
                      if (ids.length > 1) return `${ids.length} rules`;
                      if (currentFilters.containerIds?.length)
                        return `${currentFilters.containerIds.length} containers`;
                      return 'Active';
                    })()}
                  </span>
                  <button
                    onClick={clearFilters}
                    className="flex items-center gap-1 text-info transition-colors hover:brightness-110"
                    title="Clear filter"
                  >
                    <X className="w-3 h-3" />
                    <span>Clear</span>
                  </button>
                </div>
              )}
              {!hasRealData && !hideSampleData && (
                <div className="flex items-center space-x-2">
                  <span className="rounded-md bg-foreground/10 px-2 py-1 text-xs text-neutral">
                    Sample data
                  </span>
                  <button
                    onClick={toggleSampleData}
                    className="p-1 text-neutral transition-colors hover:text-text"
                    title="Hide sample data"
                  >
                    <Eye className="w-4 h-4" />
                  </button>
                </div>
              )}
            </div>
          </div>

          {pieData.length > 0 ? (
            <div
              className={`grid grid-cols-1 md:grid-cols-3 gap-4 ${!hasRealData ? 'opacity-60' : ''}`}
            >
              {/* Chart */}
              <div ref={pieContainerRef} className="md:col-span-2" style={{ width: '100%', height: 300, position: 'relative' }}>
                {isPieChartVisible && (
                  <PieChart width={Math.floor(pieChartWidth)} height={Math.floor(pieChartHeight)}>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      innerRadius={48}
                      outerRadius={84}
                      dataKey="count"
                      nameKey="name"
                      onClick={handlePieClick}
                      label={renderSliceLabel}
                      labelLine={false}
                      style={{ cursor: hasRealData ? 'pointer' : 'default' }}
                    >
                      {pieData.map((entry, index) => (
                        <Cell
                          key={`cell-${index}`}
                          fill={entry.id === 'other' ? neutralChartColor : getChartSeriesColor(entry.id)}
                          opacity={activeSlice === null || activeSlice === index ? 1 : 0.5}
                          onMouseEnter={(e) => handleSliceEnter(e, index)}
                          onMouseLeave={handleSliceLeave}
                        />
                      ))}
                    </Pie>
                    <Tooltip
                      content={({ active, payload }) => {
                        if (active && payload && payload.length) {
                          const p = payload[0].payload as { name: string; count: number };
                          const pct = totalPie ? Math.round((p.count / totalPie) * 100) : 0;
                          return (
                            <div className="rounded-md border border-divider bg-background p-2 text-sm text-text shadow">
                              <div className="font-semibold text-text">
                                {p.name}
                              </div>
                              <div className="text-neutral">
                                {p.count} - {pct}%
                              </div>
                            </div>
                          );
                        }
                        return null;
                      }}
                    />
                  </PieChart>
                )}
                {/* Donut center summary */}
                <div className="absolute inset-0 flex items-center justify-center pointer-events-none">
                  <div className="text-center">
                    <div className="text-xs text-neutral">Total</div>
                    <div className="text-xl font-bold text-text">
                      {totalPie}
                    </div>
                  </div>
                </div>
              </div>
              {/* Legend */}
              <div className="md:col-span-1 overflow-y-auto overflow-x-hidden max-h-[300px] pr-2">
                <ul className="space-y-2">
                  {pieData.map((item, idx) => {
                    const pct = totalPie ? Math.round((item.count / totalPie) * 100) : 0;
                    const color = item.id === 'other' ? neutralChartColor : getChartSeriesColor(item.id);
                    const isActive = activeSlice === idx;
                    return (
                      <li
                        key={item.id + idx}
                        className={`grid h-9 grid-cols-[1fr,96px] items-center text-sm ${isActive ? 'rounded-md bg-foreground/10' : ''}`}
                        onMouseEnter={() => setActiveSlice(idx)}
                        onMouseLeave={handleSliceLeave}
                        onClick={() => handlePieClick(item)}
                        style={{ cursor: hasRealData && item.id !== 'other' ? 'pointer' : 'default' }}
                      >
                        <div className="flex items-center gap-2 py-1.5 min-w-0">
                          <span
                            className="inline-block w-3 h-3 rounded"
                            style={{ backgroundColor: color }}
                          />
                          <span
                            className="w-full truncate text-text"
                            title={item.name}
                            aria-label={item.name}
                          >
                            {item.name}
                          </span>
                        </div>
                        <div className="w-[96px] text-right tabular-nums text-neutral">
                          {item.count} - {pct}%
                        </div>
                      </li>
                    );
                  })}
                </ul>
              </div>
            </div>
          ) : (
            <div className="h-72 flex items-center justify-center">
              <div className="text-center">
                <BarChart3 className="mx-auto mb-3 h-12 w-12 text-neutral/60" />
                <p className="text-neutral">No alert data to display</p>
                {hideSampleData && (
                  <button
                    onClick={toggleSampleData}
                    className="mx-auto mt-2 flex items-center space-x-1 text-sm text-info transition-colors hover:brightness-110"
                  >
                    <Eye className="w-4 h-4" />
                    <span>Show sample data</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </Card>

        {/* Timeline Chart */}
        <Card className="p-6">
          <h3 className="mb-4 text-lg font-bold text-text">
            Alert Timeline
          </h3>
          <div ref={timelineContainerRef} style={{ width: '100%', height: 300 }}>
            {isTimelineChartVisible && (
              <AreaChart width={Math.floor(chartWidth)} height={Math.floor(timelineChartHeight)} data={timelineData}>
                <CartesianGrid strokeDasharray="3 3" stroke={chartSurfaceColors.grid} />
                <XAxis
                  dataKey="time"
                  stroke={chartSurfaceColors.muted}
                  tick={{
                    fontSize: breakpoint === 'mobile' ? 10 : 12,
                    fill: chartSurfaceColors.tooltipText,
                  }}
                  angle={tickConfig.rotation}
                  textAnchor={tickConfig.rotation < 0 ? 'end' : 'middle'}
                  height={Math.abs(tickConfig.rotation) > 0 ? 70 : 50}
                  interval={tickConfig.stepSize - 1}
                />
                <YAxis
                  stroke={chartSurfaceColors.muted}
                  tick={{ fill: chartSurfaceColors.tooltipText }}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: chartSurfaceColors.tooltipBackground,
                    border: `1px solid ${chartSurfaceColors.grid}`,
                    borderRadius: '6px',
                    padding: '8px 12px',
                  }}
                  labelStyle={{
                    color: chartSurfaceColors.tooltipText,
                    fontWeight: 600,
                    marginBottom: '4px',
                  }}
                  itemStyle={{
                    color: chartSurfaceColors.tooltipText,
                    padding: '2px 0',
                  }}
                  labelFormatter={(label, payload) => {
                    if (payload && payload[0]) {
                      return (payload[0].payload as { fullTimestamp?: string })?.fullTimestamp || label;
                    }
                    return label;
                  }}
                />
                <Area
                  type="monotone"
                  dataKey="alerts"
                  stroke={timelineColor}
                  fill={timelineColor}
                  fillOpacity={0.3}
                />
                {/*
                  Brush is uncontrolled and stable thanks to snapshot approach - data only changes
                  when user explicitly clicks "Refresh Stats", eliminating the flicker that occurred
                  with live updates. User's zoom selection persists until they refresh or change filters.
                */}
                <Brush dataKey="time" height={30} stroke={timelineColor} />
              </AreaChart>
            )}
          </div>
        </Card>
      </div>
    </div>
  );
};

export default AlertStatsPage;
