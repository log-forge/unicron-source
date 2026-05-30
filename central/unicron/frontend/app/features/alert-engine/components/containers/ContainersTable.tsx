import React, { useState, useEffect, useRef, useMemo } from "react";
import Card from "../ui/Card";
import { Container, ChevronDown, ChevronRight, Users, Search } from "lucide-react";
import type { ContainerInfo, GroupInfo } from "../../types";
import { getStatusBadgeClasses } from "~/utils/theme";

interface ContainersTableProps {
  containers: ContainerInfo[];
  groups: GroupInfo[];
}

type FilterMode = 'all' | 'standalone' | string;

// Helper function for date formatting
function formatLocalDateTime(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleString();
}

// Create a persistent store for expanded groups outside of component
const expandedGroupsStore = {
  groups: new Set<number | string>(),
  listeners: new Set<(groups: Set<number | string>) => void>(),

  toggle(groupId: number | string) {
    if (this.groups.has(groupId)) {
      this.groups.delete(groupId);
    } else {
      this.groups.add(groupId);
    }
    this.notify();
  },

  subscribe(listener: (groups: Set<number | string>) => void) {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  },

  notify() {
    this.listeners.forEach(listener => listener(new Set(this.groups)));
  }
};

const ContainersTable: React.FC<ContainersTableProps> = React.memo(({ containers, groups }) => {
  const [expandedGroups, setExpandedGroups] = useState<Set<number | string>>(expandedGroupsStore.groups);
  const hasInitiallyLoadedRef = useRef(false);
  const [filter, setFilter] = useState<FilterMode>('all');
  const [search, setSearch] = useState('');

  // Subscribe to the persistent expanded groups store
  useEffect(() => {
    const unsubscribe = expandedGroupsStore.subscribe(setExpandedGroups);

    // Mark as initially loaded after first data load
    if (!hasInitiallyLoadedRef.current && containers.length > 0) {
      hasInitiallyLoadedRef.current = true;
    }

    return unsubscribe;
  }, [containers.length]);

  const toggleGroup = (groupId: number | string) => {
    expandedGroupsStore.toggle(groupId);
  };

  const getContainerKey = (container: ContainerInfo) => {
    const hostId = container.host_id || 'local';
    return `${hostId}:${container.name}`;
  };

  const getContainerByKey = (containerKey: string): ContainerInfo | undefined => {
    return containers.find(c => getContainerKey(c) === containerKey);
  };

  // Extract unique compose stacks from container labels
  const composeStacks = useMemo(() => {
    const stacks = new Set<string>();
    containers.forEach(c => {
      const stack = c.labels?.['com.docker.compose.project'];
      if (stack) stacks.add(stack);
    });
    return Array.from(stacks).sort();
  }, [containers]);

  // Filter containers based on selected filter and search
  const filteredContainers = useMemo(() => {
    return containers.filter(c => {
      // Search filter
      if (search) {
        const searchLower = search.toLowerCase();
        if (!c.name.toLowerCase().includes(searchLower) &&
            !c.image_name.toLowerCase().includes(searchLower) &&
            !(c.host_id || 'local').toLowerCase().includes(searchLower)) {
          return false;
        }
      }

      // Compose stack filter
      if (filter === 'all') return true;
      if (filter === 'standalone') {
        return !c.labels?.['com.docker.compose.project'];
      }
      // Filter by specific stack
      return c.labels?.['com.docker.compose.project'] === filter;
    });
  }, [containers, filter, search]);

  // Filter groups to only include those with containers matching filter
  const filteredGroups = useMemo(() => {
    if (filter === 'all' && !search) return groups;
    return groups.filter(group => {
      return group.containerIds.some(containerKey => {
        const container = getContainerByKey(containerKey);
        if (!container) return false;
        return filteredContainers.some(fc => fc.identifier === container.identifier);
      });
    });
  }, [groups, filter, search, filteredContainers]);

  // Get containers not in any group
  const standaloneContainers = useMemo(() => {
    return filteredContainers.filter(
      container => !groups.some(group => group.containerIds.includes(getContainerKey(container)))
    );
  }, [filteredContainers, groups]);

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap gap-4 items-center">
        <div className="relative flex-1 min-w-[200px]">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-4 h-4 text-neutral-text" />
          <input
            type="text"
            placeholder="Search containers..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-full pl-10 pr-4 py-2 border border-divider rounded-lg shadow-sm focus:ring-2 focus:ring-primary/40 focus:border-primary dark:bg-foreground dark:border-divider dark:text-text text-sm"
          />
        </div>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          className="px-4 py-2 border border-divider rounded-lg shadow-sm focus:ring-2 focus:ring-primary/40 focus:border-primary dark:bg-foreground dark:border-divider dark:text-text text-sm"
        >
          <option value="all">All Containers</option>
          <option value="standalone">Ungrouped</option>
          {composeStacks.map(stack => (
            <option key={stack} value={stack}>{stack}</option>
          ))}
        </select>
      </div>

      {/* Container count */}
      <div className="text-sm text-neutral-text dark:text-neutral-text">
        Showing {filteredContainers.length} of {containers.length} containers
        {filteredGroups.length > 0 && ` in ${filteredGroups.length} group${filteredGroups.length !== 1 ? 's' : ''}`}
      </div>

      <Card className="overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full">
            <thead>
              <tr className="bg-gradient-to-r from-foreground/70 to-alt-foreground dark:from-foreground dark:to-alt-foreground border-b border-divider/60 dark:border-divider">
                <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Container/Group</th>
                <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Host</th>
                <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Status</th>
                <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Image</th>
                <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Stack</th>
                <th className="px-6 py-4 text-left text-xs font-bold text-text uppercase tracking-wider">Last Seen</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-divider/40 dark:divide-divider dark:bg-foreground">
              {/* Render individual containers not in groups */}
              {standaloneContainers.map((container, index) => (
                <tr
                  key={container.identifier}
                  className={`hover:bg-foreground/70 dark:hover:bg-alt-foreground/50 transition-colors duration-200 group ${!hasInitiallyLoadedRef.current ? 'animate-fade-in' : ''}`}
                  style={!hasInitiallyLoadedRef.current ? {animationDelay: `${index * 50}ms`} : {}}
                >
                  <td className="px-6 py-5">
                    <div className="flex items-center">
                      <div className="p-2 bg-gradient-to-br from-info/15 to-info/15 dark:from-info/30 dark:to-info/30 rounded-xl mr-4 group-hover:from-info/15 group-hover:to-info/15 dark:group-hover:from-info/40 dark:group-hover:to-info/40 transition-all duration-200">
                        <Container className="w-5 h-5 text-info dark:text-info" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-text dark:text-text truncate">{container.name}</div>
                      </div>
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="text-sm text-text dark:text-neutral-text font-medium">
                      {container.host_id || 'local'}
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${getStatusBadgeClasses(container.status)}`}>
                      {container.status || 'unknown'}
                    </span>
                  </td>
                  <td className="px-6 py-5">
                    <div className="text-sm text-text dark:text-neutral-text font-medium truncate max-w-[200px]" title={container.image_name}>
                      {container.image_name || 'N/A'}
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="text-sm text-neutral-text dark:text-neutral-text">
                      {container.labels?.['com.docker.compose.project'] || '-'}
                    </div>
                  </td>
                  <td className="px-6 py-5">
                    <div className="text-sm text-neutral-text dark:text-neutral-text font-mono">{formatLocalDateTime(container.last_seen)}</div>
                  </td>
                </tr>
              ))}

              {/* Render groups with fixed height to prevent layout shift */}
              {filteredGroups.map((group, groupIndex) => (
                <React.Fragment key={`group-${group.groupId}`}>
                  {/* Group header row */}
                  <tr
                    className={`cursor-pointer border-b border-divider bg-info/10 transition-all duration-200 hover:bg-info/15 ${!hasInitiallyLoadedRef.current ? 'animate-fade-in' : ''}`}
                    onClick={() => toggleGroup(group.groupId)}
                    style={!hasInitiallyLoadedRef.current ? {animationDelay: `${groupIndex * 100}ms`} : {}}
                  >
                    <td className="px-6 py-5">
                      <div className="flex items-center">
                        <div className="p-1.5 mr-2 transition-all duration-200 border border-transparent rounded-md hover:border-divider dark:hover:border-divider">
                          {expandedGroups.has(group.groupId) ? (
                            <ChevronDown className="w-5 h-5 text-neutral-text dark:text-neutral-text" />
                          ) : (
                            <ChevronRight className="w-5 h-5 text-neutral-text dark:text-neutral-text" />
                          )}
                        </div>
                        <div className="mr-4 rounded-xl border border-info/30 bg-info/15 p-2">
                          <Users className="w-5 h-5 text-info" />
                        </div>
                        <div className="min-w-0">
                          <div className="text-sm font-bold text-text dark:text-text truncate">
                            {group.name || `Group ${group.groupId}`}
                          </div>
                          <div className="text-xs text-neutral-text dark:text-neutral-text">
                            {group.containerIds.length} containers
                            {group.monitoredContainerCount !== undefined && (
                              <span className="ml-1 font-medium text-success">
                                ({group.monitoredContainerCount} monitored)
                              </span>
                            )}
                          </div>
                        </div>
                      </div>
                    </td>
                    <td className="px-6 py-5">
                      <span className="text-neutral-text dark:text-neutral-text">-</span>
                    </td>
                    <td className="px-6 py-5">
                      <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${getStatusBadgeClasses("group")}`}>
                        Group
                      </span>
                    </td>
                    <td className="px-6 py-5">
                      <span className="text-neutral-text dark:text-neutral-text">-</span>
                    </td>
                    <td className="px-6 py-5">
                      <span className="text-neutral-text dark:text-neutral-text">-</span>
                    </td>
                    <td className="px-6 py-5">
                      <span className="text-neutral-text dark:text-neutral-text">-</span>
                    </td>
                  </tr>

                  {/* Group containers with smooth expand/collapse */}
                  <tr className={`transition-all duration-300 ease-in-out ${
                    expandedGroups.has(group.groupId) ? 'opacity-100' : 'opacity-0 max-h-0 overflow-hidden'
                  }`}>
                    <td colSpan={6} className="p-0">
                      <div className={`transition-all duration-300 ease-in-out ${
                        expandedGroups.has(group.groupId) ? 'max-h-screen' : 'max-h-0 overflow-hidden'
                      }`}>
                        <table className="w-full">
                          <tbody>
                            {group.containerIds.map((containerKey, containerIndex) => {
                              const container = getContainerByKey(containerKey);
                              if (!container) return null;
                              // Check if container matches filter
                              if (!filteredContainers.some(fc => fc.identifier === container.identifier)) return null;

                              return (
                                <tr
                                  key={`${group.groupId}-${container.identifier}`}
                                  className={`hover:bg-info/10 dark:hover:bg-neutral/30 transition-colors duration-200 bg-info/5 dark:bg-foreground/20 ${!hasInitiallyLoadedRef.current ? 'animate-slide-up' : ''}`}
                                  style={!hasInitiallyLoadedRef.current ? {animationDelay: `${containerIndex * 100}ms`} : {}}
                                >
                                  <td className="px-6 py-4">
                                    <div className="flex items-center ml-8">
                                      <div className="p-1.5 bg-gradient-to-br from-info/15 to-info/15 dark:from-info/30 dark:to-info/30 rounded-lg mr-3">
                                        <Container className="w-4 h-4 text-info dark:text-info" />
                                      </div>
                                      <div className="min-w-0">
                                        <div className="text-sm font-medium text-text dark:text-text truncate">{container.name}</div>
                                      </div>
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <div className="text-sm text-text dark:text-neutral-text font-medium">
                                      {container.host_id || 'local'}
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <span className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-medium ${getStatusBadgeClasses(container.status)}`}>
                                      {container.status || 'unknown'}
                                    </span>
                                  </td>
                                  <td className="px-6 py-4">
                                    <div className="text-sm text-text dark:text-neutral-text truncate max-w-[200px]" title={container.image_name}>
                                      {container.image_name || 'N/A'}
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <div className="text-sm text-neutral-text dark:text-neutral-text">
                                      {container.labels?.['com.docker.compose.project'] || '-'}
                                    </div>
                                  </td>
                                  <td className="px-6 py-4">
                                    <div className="text-sm text-neutral-text dark:text-neutral-text font-mono">{formatLocalDateTime(container.last_seen)}</div>
                                  </td>
                                </tr>
                              );
                            })}
                          </tbody>
                        </table>
                      </div>
                    </td>
                  </tr>
                </React.Fragment>
              ))}
            </tbody>
          </table>
          {containers.length === 0 && groups.length === 0 && (
            <div className="text-center py-16">
              <div className="p-6 bg-gradient-to-br from-alt-foreground to-neutral/20 dark:from-alt-foreground dark:to-neutral/60 rounded-3xl w-24 h-24 mx-auto mb-6 flex items-center justify-center">
                <Container className="w-12 h-12 text-neutral-text dark:text-neutral-text" />
              </div>
              <h3 className="text-lg font-semibold text-text dark:text-text mb-2">No containers registered</h3>
              <p className="text-neutral-text dark:text-neutral-text">Connect a Herald agent to see containers here.</p>
            </div>
          )}
          {containers.length > 0 && filteredContainers.length === 0 && (
            <div className="text-center py-16">
              <div className="p-6 bg-gradient-to-br from-alt-foreground to-neutral/20 dark:from-alt-foreground dark:to-neutral/60 rounded-3xl w-24 h-24 mx-auto mb-6 flex items-center justify-center">
                <Search className="w-12 h-12 text-neutral-text dark:text-neutral-text" />
              </div>
              <h3 className="text-lg font-semibold text-text dark:text-text mb-2">No containers match filter</h3>
              <p className="text-neutral-text dark:text-neutral-text">Try adjusting your search or filter criteria.</p>
            </div>
          )}
        </div>
      </Card>
    </div>
  );
});

export default ContainersTable;
