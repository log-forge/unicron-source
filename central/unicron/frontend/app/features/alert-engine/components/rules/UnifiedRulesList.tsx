import { useState, useMemo, useEffect, useRef } from "react";
import type { AlertRule } from "../../types";
import Button from "../ui/Button";
import Card from "../ui/Card";
import Badge from "../ui/Badge";
import { generateRuleDescription } from "../../utils/ruleHelpers";
import {
  Edit,
  Trash2,
  Play,
  Pause,
  Shield,
  RefreshCw,
  Search,
  Filter,
  ChevronDown,
  ChevronRight,
  CheckSquare,
  Square
} from "lucide-react";

interface UnifiedRulesListProps {
  rules: AlertRule[];
  onDelete: (id: string) => void;
  onEdit: (rule: AlertRule) => void;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  onBulkToggle?: (ruleIds: string[], enabled: boolean) => void;
  showCreateButton?: boolean;
  onCreateClick?: () => void;
  canManageRules?: boolean;
}

// Removed unused categoryIcons for now

const tagColors = {
  // Category tags
  'Stability': 'bg-info/15 text-info border border-info/30',
  'Performance': 'bg-success/15 text-success border border-success/30',
  'Logs': 'bg-secondary/15 text-secondary border border-secondary/30',
  'Security': 'bg-error/15 text-error border border-error/30',
  // Type tags
  'Metrics': 'bg-warning/15 text-warning border border-warning/30',
  'Events': 'bg-primary/15 text-primary border border-primary/30',
  // Action tags
  'Notify': 'bg-neutral/10 text-neutral border border-neutral/30',
  'Restart': 'bg-warning/15 text-warning border border-warning/30',
  'Stop': 'bg-error/15 text-error border border-error/30',
  'Kill': 'bg-error/20 text-error border border-error/40',
  'Start': 'bg-success/15 text-success border border-success/30',
  // Special tags
  'Template': 'bg-success/15 text-success border border-success/30',
  // Default
  'default': 'bg-neutral/10 text-neutral border border-neutral/30'
};

export default function UnifiedRulesList({
  rules,
  onDelete,
  onEdit,
  onToggleEnabled,
  onBulkToggle,
  showCreateButton = true,
  onCreateClick,
  canManageRules = true
}: UnifiedRulesListProps) {
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [groupBy, setGroupBy] = useState<'none' | 'tag' | 'container' | 'category' | 'action' | 'state'>('none');
  const [sortBy, setSortBy] = useState<'updated-newest' | 'updated-oldest' | 'created-newest' | 'created-oldest' | 'name-az' | 'name-za' | 'state'>('updated-newest');
  const [showFilters, setShowFilters] = useState(false);
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [hideDisabled, setHideDisabled] = useState(false);
  const [expandedRules, setExpandedRules] = useState<Set<string>>(new Set());
  const prevGroupByRef = useRef(groupBy);
  const [selectedRuleIds, setSelectedRuleIds] = useState<Set<string>>(new Set());
  const [isBulkToggling, setIsBulkToggling] = useState(false);

  // Get all unique tags from rules
  const allTags = useMemo(() => {
    const tagsSet = new Set<string>();
    rules.forEach(rule => {
      rule.tags?.forEach(tag => tagsSet.add(tag));
    });
    return Array.from(tagsSet).sort();
  }, [rules]);

  // Filter and sort rules
  const filteredRules = useMemo(() => {
    let filtered = rules.filter(rule => {
      // Search filter
      const matchesSearch = !searchQuery ||
        rule.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        rule.tags?.some(tag => tag.toLowerCase().includes(searchQuery.toLowerCase()));

      // Tag filter
      const matchesTags = selectedTags.length === 0 ||
        selectedTags.every(selectedTag => rule.tags?.includes(selectedTag));

      // Disabled filter
      const matchesDisabled = !hideDisabled || rule.enabled;

      return matchesSearch && matchesTags && matchesDisabled;
    });

    // Sort rules based on selected criteria
    filtered.sort((a, b) => {
      // State sorting always puts enabled before disabled
      const stateSort = () => {
        if (a.enabled && !b.enabled) return -1;
        if (!a.enabled && b.enabled) return 1;
        return 0;
      };

      switch (sortBy) {
        case 'updated-newest':
        case 'updated-oldest':
          // State first, then by updated (using ID as proxy)
          const stateResult1 = stateSort();
          if (stateResult1 !== 0) return stateResult1;
          return sortBy === 'updated-newest' ? b.id.localeCompare(a.id) : a.id.localeCompare(b.id);

        case 'created-newest':
        case 'created-oldest':
          const stateResult2 = stateSort();
          if (stateResult2 !== 0) return stateResult2;
          return sortBy === 'created-newest' ? b.id.localeCompare(a.id) : a.id.localeCompare(b.id);

        case 'name-az':
        case 'name-za':
          const stateResult3 = stateSort();
          if (stateResult3 !== 0) return stateResult3;
          return sortBy === 'name-az' ? a.name.localeCompare(b.name) : b.name.localeCompare(a.name);

        case 'state':
          // State only, then name as tiebreaker
          const stateResult4 = stateSort();
          return stateResult4 !== 0 ? stateResult4 : a.name.localeCompare(b.name);

        default:
          return 0;
      }
    });

    return filtered;
  }, [rules, searchQuery, selectedTags, sortBy, hideDisabled]);

  // Group the filtered and sorted rules
  const groupedRules = useMemo(() => {
    if (groupBy === 'none') {
      return [{ key: 'all', title: '', rules: filteredRules, count: filteredRules.length }];
    }

    const groups: { [key: string]: AlertRule[] } = {};

    filteredRules.forEach(rule => {
      let groupKeys: string[] = [];

      switch (groupBy) {
        case 'tag':
          groupKeys = rule.tags && rule.tags.length > 0 ? rule.tags : ['untagged'];
          break;
        case 'container':
          if (rule.scope_type === 'herald' && rule.scope_targets?.length) {
            groupKeys = [`All on: ${rule.scope_targets[0]}`];
          } else if (rule.scope_type === 'global') {
            groupKeys = ['All Containers (legacy)'];
          } else if (rule.scope_type === 'container' && rule.scope_targets) {
            groupKeys = rule.scope_targets;
          } else {
            groupKeys = ['Other'];
          }
          break;
        case 'category':
          // Derive category from tags
          const categoryTags = ['Stability', 'Performance', 'Logs', 'Security'];
          const ruleCategories = rule.tags?.filter(tag => categoryTags.includes(tag)) || [];
          groupKeys = ruleCategories.length > 0 ? ruleCategories : ['Other'];
          break;
        case 'action':
          // Get action types from rule actions or legacy action_type
          if (rule.actions && rule.actions.length > 0) {
            const actionTypes: string[] = rule.actions.map(action => {
              switch (action.type) {
                case 'notification': return 'Notify';
                case 'restart_container': return 'Restart';
                case 'kill_container': return 'Kill';
                case 'stop_container': return 'Stop';
                case 'start_container': return 'Start';
                default: return action.type;
              }
            });
            groupKeys = [...new Set(actionTypes)];
          } else {
            // Fallback to legacy action_type
            switch (rule.action_type) {
              case 'notification': groupKeys = ['Notify']; break;
              case 'restart_container': groupKeys = ['Restart']; break;
              case 'kill_container': groupKeys = ['Kill']; break;
              case 'stop_container': groupKeys = ['Stop']; break;
              case 'start_container': groupKeys = ['Start']; break;
              default: groupKeys = ['Other'];
            }
          }
          break;
        case 'state':
          groupKeys = [rule.enabled ? 'Enabled' : 'Disabled'];
          break;
        default:
          groupKeys = ['Other'];
      }

      // Add rule to each group it belongs to
      groupKeys.forEach(key => {
        if (!groups[key]) {
          groups[key] = [];
        }
        groups[key].push(rule);
      });
    });

    // Convert to array and sort groups
    const groupArray = Object.keys(groups)
      .sort((a, b) => {
        // Special ordering for certain group types
        if (groupBy === 'state') {
          if (a === 'Enabled' && b === 'Disabled') return -1;
          if (a === 'Disabled' && b === 'Enabled') return 1;
        }
        if (a === 'untagged' || a === 'Other') return 1;
        if (b === 'untagged' || b === 'Other') return -1;
        return a.localeCompare(b);
      })
      .map(key => ({
        key,
        title: key,
        rules: groups[key],
        count: groups[key].length
      }));

    return groupArray;
  }, [filteredRules, groupBy]);

  // Collapse all groups by default when grouping mode changes
  useEffect(() => {
    // Only collapse when groupBy actually changes, not when the grouped list reshuffles
    if (prevGroupByRef.current !== groupBy) {
      if (groupBy !== 'none' && groupedRules.length > 0) {
        const allGroupKeys = new Set(groupedRules.map(group => group.key));
        setCollapsedGroups(allGroupKeys);
      } else if (groupBy === 'none') {
        setCollapsedGroups(new Set());
      }
      prevGroupByRef.current = groupBy;
    }
  }, [groupBy, groupedRules]);

  const getTagColor = (tag: string): string => {
    return tagColors[tag as keyof typeof tagColors] || tagColors.default;
  };

  const toggleGroup = (groupKey: string) => {
    const newCollapsed = new Set(collapsedGroups);
    if (newCollapsed.has(groupKey)) {
      newCollapsed.delete(groupKey);
    } else {
      newCollapsed.add(groupKey);
    }
    setCollapsedGroups(newCollapsed);
  };

  const scrollToGroup = (groupKey: string) => {
    // Ensure the group is expanded
    const newCollapsed = new Set(collapsedGroups);
    if (newCollapsed.has(groupKey)) {
      newCollapsed.delete(groupKey);
      setCollapsedGroups(newCollapsed);
    }

    // Scroll to the group header
    setTimeout(() => {
      const element = document.getElementById(`group-${groupKey}`);
      if (element) {
        element.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    }, 100); // Small delay to allow for state update
  };

  const toggleTagFilter = (tag: string) => {
    setSelectedTags(prev =>
      prev.includes(tag)
        ? prev.filter(t => t !== tag)
        : [...prev, tag]
    );
  };

  const clearFilters = () => {
    setSearchQuery('');
    setSelectedTags([]);
  };

  const toggleRuleExpanded = (ruleId: string) => {
    setExpandedRules(prev => {
      const newSet = new Set(prev);
      if (newSet.has(ruleId)) {
        newSet.delete(ruleId);
      } else {
        newSet.add(ruleId);
      }
      return newSet;
    });
  };

  // Bulk selection handlers
  const handleSelectAll = () => {
    if (selectedRuleIds.size === filteredRules.length && filteredRules.length > 0) {
      setSelectedRuleIds(new Set());
    } else {
      setSelectedRuleIds(new Set(filteredRules.map(r => r.id)));
    }
  };

  const handleSelectRule = (ruleId: string) => {
    const newSelection = new Set(selectedRuleIds);
    if (newSelection.has(ruleId)) {
      newSelection.delete(ruleId);
    } else {
      newSelection.add(ruleId);
    }
    setSelectedRuleIds(newSelection);
  };

  const handleBulkToggle = async (enabled: boolean) => {
    if (!onBulkToggle) return;
    setIsBulkToggling(true);
    try {
      await onBulkToggle(Array.from(selectedRuleIds), enabled);
      setSelectedRuleIds(new Set());
    } finally {
      setIsBulkToggling(false);
    }
  };

  const allSelected = filteredRules.length > 0 && selectedRuleIds.size === filteredRules.length;

  const renderRuleCard = (rule: AlertRule, currentGroup?: string) => {
    const isTemplate = !!rule.template_source;
    const isDisabled = !rule.enabled;

    // Get other groups this rule appears in (for multi-tag display)
    const getOtherGroups = (): string[] => {
      if (groupBy === 'none' || !currentGroup) return [];

      const otherGroups: string[] = [];

      switch (groupBy) {
        case 'tag':
          const ruleTags = rule.tags || [];
          return ruleTags.filter(tag => tag !== currentGroup);
        case 'category':
          const categoryTags = ['Stability', 'Performance', 'Logs', 'Security'];
          const ruleCategories = rule.tags?.filter(tag => categoryTags.includes(tag)) || [];
          return ruleCategories.filter(category => category !== currentGroup);
        case 'action':
          if (rule.actions && rule.actions.length > 0) {
            const actionTypes: string[] = rule.actions.map(action => {
              switch (action.type) {
                case 'notification': return 'Notify';
                case 'restart_container': return 'Restart';
                case 'kill_container': return 'Kill';
                case 'stop_container': return 'Stop';
                case 'start_container': return 'Start';
                default: return action.type;
              }
            });
            return [...new Set(actionTypes)].filter(action => action !== currentGroup);
          }
          break;
      }

      return otherGroups;
    };

    const otherGroups = getOtherGroups();
    const toggleTitle = isTemplate
      ? (rule.enabled ? 'Disable template rule' : 'Enable template rule')
      : (rule.enabled ? 'Disable rule' : 'Enable rule');

    const toggleClassName = rule.enabled
      ? 'text-warning hover:bg-warning/10'
      : 'text-success bg-background border border-success/30 hover:bg-success/10 opacity-100';


    return (
      <Card
        key={rule.id}
        className={`p-6 hover:shadow-md transition-all ${
          isDisabled ? 'opacity-60 bg-foreground/70 dark:bg-foreground/60' : ''
        }`}
      >
        <div className="flex items-start justify-between">
          {/* Bulk selection checkbox */}
          {canManageRules && onBulkToggle && (
            <button
              onClick={(e) => { e.stopPropagation(); handleSelectRule(rule.id); }}
              className="mr-3 mt-1 flex-shrink-0"
              title={selectedRuleIds.has(rule.id) ? "Deselect rule" : "Select rule"}
            >
              {selectedRuleIds.has(rule.id) ? (
                <CheckSquare className="w-5 h-5 text-primary" />
              ) : (
                <Square className="w-5 h-5 text-neutral-text hover:text-neutral-text" />
              )}
            </button>
          )}
          <div className="flex-1">
            {/* Rule name and template badge */}
            <div className="flex items-center gap-2 mb-2">
              <h3 className={`text-lg font-semibold ${isDisabled ? 'text-neutral-text' : 'text-text'}`}>
                {rule.name}
              </h3>
              {isDisabled && (
                <Badge variant="default" size="sm" title="This rule is disabled">
                  Disabled
                </Badge>
              )}
              {isTemplate && (
                <Badge variant="success" size="sm" title="This rule was created from a template">
                  Template
                </Badge>
              )}
            </div>

            {/* Rule details */}
            <div className="text-sm text-neutral-text mb-3">
              <span className="capitalize">{rule.trigger_type.replace('_', ' ')}</span>
              {rule.timeline_minutes && (
                <span> * {rule.timeline_minutes} min window</span>
              )}
              {rule.timeline_count && (
                <span> * {rule.timeline_count} occurrences</span>
              )}
            </div>

            {/* Tags */}
            {rule.tags && rule.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-3">
                {rule.tags.map(tag => (
                  <button
                    key={tag}
                    onClick={() => toggleTagFilter(tag)}
                    className={`px-2 py-1 text-xs rounded-full transition-colors ${
                      getTagColor(tag)
                    } ${
                      selectedTags.includes(tag) ? 'ring-2 ring-offset-1 ring-primary' : 'hover:opacity-80'
                    }`}
                    title={`Filter by ${tag} tag`}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}

            {/* Also in other groups (for multi-tag rules) */}
            {otherGroups.length > 0 && (
              <div className="flex flex-wrap items-center gap-1 mb-3 text-xs text-neutral-text">
                <span>Also in:</span>
                {otherGroups.slice(0, 2).map(group => (
                  <button
                    key={group}
                    onClick={() => scrollToGroup(group)}
                    className="px-2 py-0.5 bg-alt-foreground text-text rounded-full hover:bg-neutral/20 transition-colors"
                    title={`Jump to ${group} group`}
                  >
                    {group}
                  </button>
                ))}
                {otherGroups.length > 2 && (
                  <span
                    className="px-2 py-0.5 bg-alt-foreground text-neutral-text rounded-full cursor-help"
                    title={`Also in: ${otherGroups.slice(2).join(', ')}`}
                  >
                    +{otherGroups.length - 2} more
                  </span>
                )}
              </div>
            )}

            {/* Scope info */}
            {rule.scope_type === 'herald' && rule.scope_targets?.length ? (
              <div className="text-xs mb-2">
                <span className="inline-flex items-center rounded-full border border-info/30 bg-info/15 px-2 py-0.5 font-medium text-info">
                  All on: {rule.scope_targets.join(', ')}
                </span>
              </div>
            ) : rule.scope_type === 'global' ? (
              <div className="text-xs text-neutral-text mb-2">
                <span>Global (legacy)</span>
              </div>
            ) : rule.scope_targets?.length ? (
              <div className="text-xs text-neutral-text mb-2">
                <span className="capitalize">{rule.scope_type}: </span>
                <span>{rule.scope_targets.join(', ')}</span>
              </div>
            ) : null}
          </div>

          {/* Actions and status */}
          <div className="flex items-center gap-2 ml-4">
            {/* Expand/Collapse button */}
            <button
              onClick={() => toggleRuleExpanded(rule.id)}
              className="p-2 text-text hover:bg-info/10 hover:text-info rounded-md transition-colors border border-divider bg-background shadow-sm"
              title={expandedRules.has(rule.id) ? "Hide details" : "Show details"}
            >
              {expandedRules.has(rule.id) ?
                <ChevronDown className="w-5 h-5" /> :
                <ChevronRight className="w-5 h-5" />
              }
            </button>

            {canManageRules && (
              <>
                {/* Enabled toggle */}
                <button
                  onClick={() => onToggleEnabled(rule.id, !rule.enabled)}
                  className={`p-1 rounded transition-colors ${toggleClassName}`}
                  title={toggleTitle}
                >
                  {rule.enabled ? <Pause className="w-5 h-5" /> : <Play className="w-5 h-5" />}
                </button>

                {/* Convert to custom (only for template rules) */}
                {isTemplate && (
                  <button
                    disabled
                    className="p-1 text-neutral cursor-not-allowed rounded transition-colors opacity-50"
                    title="Template rules can only change their enabled state."
                  >
                    <RefreshCw className="w-4 h-4" />
                  </button>
                )}

                {/* Edit */}
                <button
                  onClick={() => {
                    if (isTemplate) return;
                    onEdit(rule);
                  }}
                  disabled={isTemplate}
                  className={`p-1 rounded transition-colors ${isTemplate ? 'cursor-not-allowed text-neutral-text' : 'text-neutral-text hover:bg-foreground/70'}`}
                  title={isTemplate ? 'Template rules can only change their enabled state. Convert to a custom rule to edit other settings.' : 'Edit rule'}
                >
                  <Edit className="w-4 h-4" />
                </button>

                {/* Delete */}
                <button
                  onClick={() => onDelete(rule.id)}
                  className="p-1 text-error hover:bg-error/10 rounded transition-colors"
                  title="Delete rule"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </>
            )}
          </div>
        </div>

        {/* Expanded details section */}
        {expandedRules.has(rule.id) && (
          <div className="mt-4 pt-4 border-t border-divider">
            <div className="space-y-3">
              {/* Plain English Rule Preview */}
              <div>
                <h4 className="text-sm font-medium text-text dark:text-text mb-2">Rule Preview</h4>
                <div className="bg-foreground/70 dark:bg-foreground/60 rounded-lg p-3">
                  <p className="text-sm text-neutral-text dark:text-text whitespace-pre-line">
                    {generateRuleDescription(rule, [], [])}
                  </p>
                </div>
              </div>

              {/* Detailed Scope Information */}
              <div>
                <h4 className="text-sm font-medium text-text mb-2">Scope</h4>
                <div className="text-sm text-neutral-text">
                  {rule.scope_type === 'herald' && rule.scope_targets?.length ? (
                    <span className="text-info font-medium">Host: {rule.scope_targets[0]} (all containers)</span>
                  ) : rule.scope_type === 'global' ? (
                    <div>
                      <span className="text-neutral-text">All containers (legacy global)</span>
                    </div>
                  ) : rule.scope_type === 'container' && rule.scope_targets?.length ? (
                    <div>
                      <span className="font-medium">Containers: </span>
                      <span>{rule.scope_targets.join(', ')}</span>
                    </div>
                  ) : rule.scope_type === 'group' && rule.scope_targets?.length ? (
                    <div>
                      <span className="font-medium">Groups: </span>
                      <span>{rule.scope_targets.join(', ')}</span>
                    </div>
                  ) : (
                    <span className="text-neutral-text">No specific scope defined</span>
                  )}
                </div>
              </div>

              {/* Actions Summary */}
              {rule.actions && rule.actions.length > 0 && (
                <div>
                  <h4 className="text-sm font-medium text-text mb-2">Actions</h4>
                  <div className="flex flex-wrap gap-2">
                    {rule.actions.map((action, index) => (
                      <Badge
                        key={index}
                        variant="info"
                        size="sm"
                      >
                        {action.type === 'notification' ? 'Send Notification' :
                         action.type === 'restart_container' ? 'Restart Container' :
                         action.type === 'stop_container' ? 'Stop Container' :
                         action.type === 'start_container' ? 'Start Container' :
                         action.type === 'kill_container' ? 'Kill Container' :
                         action.type}
                      </Badge>
                    ))}
                  </div>
                </div>
              )}

            </div>
          </div>
        )}
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:justify-between sm:items-center gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold text-text">All Rules</h2>
          </div>
          <p className="text-neutral-text mt-1">
            {filteredRules.length} of {rules.length} rules
            {selectedTags.length > 0 && (
              <span> * Filtered by: {selectedTags.join(', ')}</span>
            )}
          </p>
        </div>
        {showCreateButton && canManageRules && onCreateClick && (
          <Button
            onClick={() => {
              onCreateClick();
            }}
            title="Create new rule"
          >
            + Create Rule
          </Button>
        )}
      </div>

      {/* Search and filters */}
      <div className="space-y-4">
        {/* Search bar */}
        <div className="relative">
          <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 text-neutral-text w-4 h-4" />
          <input
            type="text"
            placeholder="Search rules by name or tags..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="input-modern w-full pl-9"
          />
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-4">
            <button
              onClick={() => setShowFilters(!showFilters)}
              className={`flex items-center gap-2 px-3 py-2 rounded-md text-sm transition-colors ${
                showFilters
                ? 'bg-info/15 text-info border border-info/30'
                : 'bg-alt-foreground text-text hover:bg-neutral/20 dark:bg-foreground dark:text-text dark:hover:bg-alt-foreground'
            }`}
          >
            <Filter className="w-4 h-4" />
            Filters
            {selectedTags.length > 0 && (
              <span className="bg-info text-info-950 text-xs px-2 py-0.5 rounded-full">
                {selectedTags.length}
              </span>
            )}
          </button>

          <select
            value={groupBy}
            onChange={(e) => setGroupBy(e.target.value as typeof groupBy)}
            className="px-3 py-2 border border-divider dark:border-divider rounded-md text-sm focus:ring-primary/40 focus:border-primary bg-background dark:bg-foreground dark:text-text"
          >
            <option value="none">Group by: None</option>
            <option value="tag">Group by: Tag</option>
            <option value="container">Group by: Container</option>
            <option value="category">Group by: Category</option>
            <option value="action">Group by: Action</option>
            <option value="state">Group by: State</option>
          </select>

          <select
            value={sortBy}
            onChange={(e) => setSortBy(e.target.value as typeof sortBy)}
            className="px-3 py-2 border border-divider dark:border-divider rounded-md text-sm focus:ring-primary/40 focus:border-primary bg-background dark:bg-foreground dark:text-text"
          >
            <option value="updated-newest">Sort by: Updated (Newest first)</option>
            <option value="updated-oldest">Sort by: Updated (Oldest first)</option>
            <option value="created-newest">Sort by: Created (Newest first)</option>
            <option value="created-oldest">Sort by: Created (Oldest first)</option>
            <option value="name-az">Sort by: Name (A-Z)</option>
            <option value="name-za">Sort by: Name (Z-A)</option>
            <option value="state">Sort by: State (Enabled-Disabled)</option>
          </select>

          <button
            onClick={() => setHideDisabled(!hideDisabled)}
            className={`px-3 py-1 text-sm rounded-md transition-colors ${
              hideDisabled
                ? 'bg-info/15 text-info border border-info/30'
                : 'bg-alt-foreground text-text border border-divider hover:bg-neutral/20 dark:bg-foreground dark:text-text dark:border-divider dark:hover:bg-alt-foreground'
            }`}
          >
            {hideDisabled ? 'Show Disabled' : 'Hide Disabled'}
          </button>

          {groupBy !== 'none' && (
            <button
              onClick={() => setGroupBy('none')}
              className="text-sm text-neutral-text hover:text-text"
            >
              Clear grouping
            </button>
          )}

          {(searchQuery || selectedTags.length > 0) && (
            <button
              onClick={clearFilters}
              className="text-sm text-neutral-text hover:text-text"
            >
              Clear filters
            </button>
          )}
        </div>

        {/* Tag filters */}
        {showFilters && allTags.length > 0 && (
          <div className="p-4 bg-foreground/70 dark:bg-foreground/60 rounded-lg">
            <h4 className="text-sm font-medium text-text dark:text-text mb-3">Filter by tags:</h4>
            <div className="flex flex-wrap gap-2">
              {allTags.map(tag => (
                <button
                  key={tag}
                  onClick={() => toggleTagFilter(tag)}
                  className={`px-3 py-1 text-sm rounded-full transition-colors ${
                    getTagColor(tag)
                  } ${
                    selectedTags.includes(tag)
                      ? 'ring-2 ring-primary ring-offset-1'
                      : 'hover:opacity-80'
                  }`}
                >
                  {tag}
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Bulk selection header */}
      {canManageRules && onBulkToggle && filteredRules.length > 0 && (
        <div className="flex items-center gap-3 pb-2 border-b border-divider dark:border-divider">
          <button
            onClick={handleSelectAll}
            className="flex items-center gap-2 text-sm text-text dark:text-text hover:text-text dark:hover:text-text"
          >
            {allSelected ? (
              <CheckSquare className="w-5 h-5 text-primary" />
            ) : (
              <Square className="w-5 h-5" />
            )}
            <span>Select All</span>
          </button>
          {selectedRuleIds.size > 0 && (
            <span className="text-sm text-neutral-text dark:text-neutral-text">
              {selectedRuleIds.size} selected
            </span>
          )}
        </div>
      )}

      {/* Quick filter chips */}
      {(selectedTags.length > 0 || hideDisabled) && (
        <div className="flex flex-wrap items-center gap-2 py-3 border-b border-divider dark:border-divider">

          {/* Tag filter chips */}
          {selectedTags.map(tag => (
            <button
              key={tag}
              onClick={() => toggleTagFilter(tag)}
              className={`px-3 py-1 text-sm rounded-full transition-colors ${
                getTagColor(tag)
              } hover:opacity-80 flex items-center gap-1`}
              title={`Remove ${tag} filter`}
            >
              {tag}
              <span className="text-xs">x</span>
            </button>
          ))}

          {/* Hide disabled chip */}
          {hideDisabled && (
            <button
              onClick={() => setHideDisabled(false)}
              className="px-3 py-1 text-sm rounded-full bg-neutral/20 text-text hover:bg-neutral/30 dark:bg-alt-foreground dark:text-text dark:hover:bg-neutral/60 transition-colors flex items-center gap-1"
              title="Show disabled rules"
            >
              Hide Disabled
              <span className="text-xs">x</span>
            </button>
          )}

          <button
            onClick={() => {
              clearFilters();
              setHideDisabled(false);
            }}
            className="px-2 py-1 text-xs text-neutral-text hover:text-text underline"
          >
            Clear all
          </button>
        </div>
      )}

      {/* Floating bulk action bar */}
      {selectedRuleIds.size > 0 && onBulkToggle && (
        <div className="sticky top-0 z-10 rounded-lg border border-info/30 bg-info/10 p-4 shadow-md">
          <div className="flex items-center justify-between flex-wrap gap-3">
            <span className="text-sm font-medium text-text dark:text-text">
              {selectedRuleIds.size} rule{selectedRuleIds.size !== 1 ? 's' : ''} selected
            </span>
            <div className="flex items-center gap-2">
              <button
                onClick={() => handleBulkToggle(true)}
                disabled={isBulkToggling}
                className="px-4 py-2 bg-success text-success-950 rounded-md hover:brightness-110 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {isBulkToggling ? 'Updating...' : 'Enable Selected'}
              </button>
              <button
                onClick={() => handleBulkToggle(false)}
                disabled={isBulkToggling}
                className="px-4 py-2 bg-warning text-warning-950 rounded-md hover:brightness-110 transition-colors disabled:opacity-50 disabled:cursor-not-allowed text-sm"
              >
                {isBulkToggling ? 'Updating...' : 'Disable Selected'}
              </button>
              <button
                onClick={() => setSelectedRuleIds(new Set())}
                className="px-4 py-2 bg-neutral/20 dark:bg-alt-foreground text-text dark:text-text rounded-md hover:bg-neutral/30 dark:hover:bg-neutral/60 transition-colors text-sm"
              >
                Clear Selection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Rules list */}
      {filteredRules.length > 0 ? (
        <div className="space-y-6">
          {groupedRules.map(group => (
            <div key={group.key}>
              {/* Group header (only show if grouped) */}
              {groupBy !== 'none' && (
                <div
                  id={`group-${group.key}`}
                  className="flex items-center justify-between mb-4"
                >
                  <button
                    onClick={() => toggleGroup(group.key)}
                    className="flex items-center gap-2 text-lg font-semibold text-text hover:text-text transition-colors"
                  >
                    {collapsedGroups.has(group.key) ? (
                      <ChevronRight className="w-5 h-5" />
                    ) : (
                      <ChevronDown className="w-5 h-5" />
                    )}
                    <span>{group.title}</span>
                    <span className="bg-neutral/20 text-neutral-text dark:bg-alt-foreground dark:text-text text-sm px-2 py-0.5 rounded-full">
                      {group.count}
                    </span>
                  </button>
                </div>
              )}

              {/* Group rules (show if not collapsed) */}
              {!collapsedGroups.has(group.key) && (
                <div className="space-y-4">
                  {group.rules.map(rule => renderRuleCard(rule, group.key))}
                </div>
              )}
            </div>
          ))}
        </div>
      ) : (
        <div className="w-full rounded-2xl border border-divider dark:border-divider bg-background dark:bg-foreground/50 py-12 px-8 flex flex-col items-center">
          <div className="text-neutral-text mb-3">
            {rules.length === 0 ? (
              <Shield className="w-12 h-12" />
            ) : (
              <Search className="w-12 h-12" />
            )}
          </div>
          <h3 className="text-lg font-semibold text-text dark:text-text mb-1">
            {rules.length === 0 ? 'No Rules Created' : 'No Rules Match Filters'}
          </h3>
          <p className="text-neutral-text dark:text-neutral-text text-center">
            {rules.length === 0
              ? 'Get started by creating your first rule or activating a template.'
              : 'Try adjusting your search or filter criteria to see more results.'
            }
          </p>
          {rules.length === 0 && showCreateButton && canManageRules && onCreateClick && (
            <Button
              onClick={() => {
                onCreateClick();
              }}
              className="mt-4"
              title="Create your first rule"
            >
              + Create Your First Rule
            </Button>
          )}
        </div>
      )}
    </div>
  );
}
