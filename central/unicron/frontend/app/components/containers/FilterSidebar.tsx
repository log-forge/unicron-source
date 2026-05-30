/**
 * FilterSidebar Component
 *
 * Collapsible filter panel for container overview with:
 * - Host multi-select checkboxes
 * - Status filter (running/stopped)
 * - Alert filter (has/no alerts)
 * - Text search
 *
 * Persists selections to localStorage.
 */

import React, { useState, useEffect, useMemo } from "react";
import { ChevronDown, ChevronRight, Filter, X, Search } from "lucide-react";

// ============================================================================
// Types
// ============================================================================

export interface FilterState {
  hosts: string[];
  statuses: string[];
  hasAlerts: boolean | null;
  searchText: string;
}

export interface FilterSidebarProps {
  hosts: string[];
  onFilterChange: (filters: FilterState) => void;
  initialFilters?: FilterState;
  containerCounts?: Record<string, number>;
}

// ============================================================================
// LocalStorage Helpers
// ============================================================================

const FILTER_STORAGE_KEY = "containers-filters";

function getStoredFilters(): FilterState {
  if (typeof window === "undefined") {
    return { hosts: [], statuses: [], hasAlerts: null, searchText: "" };
  }
  try {
    const stored = localStorage.getItem(FILTER_STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored);
    }
  } catch {
    // Ignore parse errors
  }
  return { hosts: [], statuses: [], hasAlerts: null, searchText: "" };
}

function setStoredFilters(filters: FilterState): void {
  if (typeof window !== "undefined") {
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(filters));
  }
}

// ============================================================================
// Checkbox Component
// ============================================================================

interface CheckboxProps {
  label: string;
  checked: boolean;
  onChange: (checked: boolean) => void;
  subtitle?: string;
}

const Checkbox: React.FC<CheckboxProps> = ({ label, checked, onChange, subtitle }) => (
  <label className="flex cursor-pointer items-start gap-sm rounded-md px-sm py-xs hover:bg-neutral/10">
    <input
      type="checkbox"
      checked={checked}
      onChange={(e) => onChange(e.target.checked)}
      className="mt-0.5 h-4 w-4 rounded border-neutral/30 text-primary focus:ring-primary"
    />
    <div className="min-w-0 flex-1">
      <span className="text-sm text-text">{label}</span>
      {subtitle && <span className="ml-xs text-xs text-neutral">({subtitle})</span>}
    </div>
  </label>
);

// ============================================================================
// Filter Section Component
// ============================================================================

interface FilterSectionProps {
  title: string;
  children: React.ReactNode;
  defaultExpanded?: boolean;
}

const FilterSection: React.FC<FilterSectionProps> = ({
  title,
  children,
  defaultExpanded = false
}) => {
  const [expanded, setExpanded] = useState(defaultExpanded);

  return (
    <div className="border-b border-neutral/10 py-sm">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between px-sm py-xs text-left"
      >
        <span className="text-xs font-semibold uppercase tracking-wide text-neutral">
          {title}
        </span>
        {expanded ? (
          <ChevronDown className="h-4 w-4 text-neutral" />
        ) : (
          <ChevronRight className="h-4 w-4 text-neutral" />
        )}
      </button>
      {expanded && <div className="mt-xs">{children}</div>}
    </div>
  );
};

// ============================================================================
// Main Component
// ============================================================================

export const FilterSidebar: React.FC<FilterSidebarProps> = ({
  hosts,
  onFilterChange,
  initialFilters,
  containerCounts = {},
}) => {
  const [isCollapsed, setIsCollapsed] = useState(false);
  const [filters, setFilters] = useState<FilterState>(() =>
    initialFilters ?? getStoredFilters()
  );

  // Persist filters and notify parent
  useEffect(() => {
    setStoredFilters(filters);
    onFilterChange(filters);
  }, [filters, onFilterChange]);

  const updateFilters = (updates: Partial<FilterState>) => {
    setFilters((prev) => ({ ...prev, ...updates }));
  };

  const clearFilters = () => {
    setFilters({ hosts: [], statuses: [], hasAlerts: null, searchText: "" });
  };

  const activeFilterCount = useMemo(() => {
    let count = 0;
    if (filters.hosts.length > 0) count += 1;
    if (filters.statuses.length > 0) count += 1;
    if (filters.hasAlerts !== null) count += 1;
    if (filters.searchText) count += 1;
    return count;
  }, [filters]);

  const sortedHosts = useMemo(() =>
    [...hosts].sort((a, b) => a.localeCompare(b)),
    [hosts]
  );

  // Keep persisted host filters aligned with currently visible host options.
  useEffect(() => {
    setFilters((prev) => {
      const validHosts = prev.hosts.filter((host) => hosts.includes(host));
      if (validHosts.length === prev.hosts.length) {
        return prev;
      }
      return { ...prev, hosts: validHosts };
    });
  }, [hosts]);

  if (isCollapsed) {
    return (
      <button
        onClick={() => setIsCollapsed(false)}
        className="flex h-10 w-10 items-center justify-center rounded-lg border border-neutral/20 bg-background shadow-sm hover:bg-neutral/10 dark:bg-neutral-900"
        title="Show filters"
      >
        <Filter className="h-5 w-5 text-neutral" />
        {activeFilterCount > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-primary text-[10px] font-bold text-white">
            {activeFilterCount}
          </span>
        )}
      </button>
    );
  }

  return (
    <div className="w-64 shrink-0 rounded-xl border border-neutral/20 bg-background shadow-sm dark:bg-neutral-900">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-neutral/10 px-md py-sm">
        <div className="flex items-center gap-xs">
          <Filter className="h-4 w-4 text-neutral" />
          <span className="text-sm font-semibold text-text">Filters</span>
          {activeFilterCount > 0 && (
            <span className="rounded-full bg-primary/10 px-1.5 py-0.5 text-xs font-medium text-primary">
              {activeFilterCount}
            </span>
          )}
        </div>
        <div className="flex items-center gap-xs">
          {activeFilterCount > 0 && (
            <button
              onClick={clearFilters}
              className="text-xs text-primary hover:underline"
            >
              Clear
            </button>
          )}
          <button
            onClick={() => setIsCollapsed(true)}
            className="rounded-md p-1 hover:bg-neutral/10"
            title="Collapse filters"
          >
            <X className="h-4 w-4 text-neutral" />
          </button>
        </div>
      </div>

      {/* Search */}
      <div className="border-b border-neutral/10 p-sm">
        <div className="relative">
          <Search className="absolute left-2 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral" />
          <input
            type="text"
            placeholder="Search containers..."
            value={filters.searchText}
            onChange={(e) => updateFilters({ searchText: e.target.value })}
            className="w-full rounded-md border border-neutral/20 bg-transparent py-1.5 pl-8 pr-3 text-sm text-text placeholder:text-neutral focus:border-primary focus:outline-none focus:ring-1 focus:ring-primary"
          />
        </div>
      </div>

      {/* Host Filter */}
      <FilterSection title="Hosts">
        <div className="max-h-48 overflow-y-auto">
          {sortedHosts.map((host) => (
            <Checkbox
              key={host}
              label={host}
              subtitle={containerCounts[host] ? `${containerCounts[host]}` : undefined}
              checked={filters.hosts.includes(host)}
              onChange={(checked) => {
                if (checked) {
                  updateFilters({ hosts: [...filters.hosts, host] });
                } else {
                  updateFilters({ hosts: filters.hosts.filter((h) => h !== host) });
                }
              }}
            />
          ))}
          {sortedHosts.length === 0 && (
            <p className="px-sm py-xs text-xs text-neutral">No hosts available</p>
          )}
        </div>
      </FilterSection>

      {/* Status Filter */}
      <FilterSection title="Status">
        <Checkbox
          label="Running"
          checked={filters.statuses.includes("running")}
          onChange={(checked) => {
            if (checked) {
              updateFilters({ statuses: [...filters.statuses, "running"] });
            } else {
              updateFilters({ statuses: filters.statuses.filter((s) => s !== "running") });
            }
          }}
        />
        <Checkbox
          label="Stopped"
          checked={filters.statuses.includes("stopped")}
          onChange={(checked) => {
            if (checked) {
              updateFilters({ statuses: [...filters.statuses, "stopped"] });
            } else {
              updateFilters({ statuses: filters.statuses.filter((s) => s !== "stopped") });
            }
          }}
        />
      </FilterSection>

      {/* Alerts Filter */}
      <FilterSection title="Alerts">
        <Checkbox
          label="Has alerts"
          checked={filters.hasAlerts === true}
          onChange={(checked) => {
            updateFilters({ hasAlerts: checked ? true : null });
          }}
        />
        <Checkbox
          label="No alerts"
          checked={filters.hasAlerts === false}
          onChange={(checked) => {
            updateFilters({ hasAlerts: checked ? false : null });
          }}
        />
      </FilterSection>
    </div>
  );
};

export default FilterSidebar;
