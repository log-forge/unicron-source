import { useState, useEffect, useMemo } from "react";
import { apiService } from "../../services/api";
import type { RuleTemplate, TemplatesByCategory, AvailableMetrics, ContainerInfo, GroupInfo, AlertRule } from "../../types";
import Button from "../ui/Button";
import Modal from "../ui/Modal";
import Card from "../ui/Card";
import MultiSelect from "../ui/MultiSelect";
import DuplicateRuleDialog from "./DuplicateRuleDialog";
import {
  Shield,
  Zap,
  FileText,
  AlertTriangle,
  Play,
  Clock,
  Hash,
  Settings,
  CheckCircle,
  AlertCircle,
  Info
} from "lucide-react";

interface RuleTemplatesProps {
  rules: AlertRule[];
  containers: ContainerInfo[];
  groups: GroupInfo[];
  onTemplateActivated: () => Promise<void> | void;
}

const categoryIcons = {
  stability: Shield,
  performance: Zap,
  logs: FileText,
  security: AlertTriangle
};

const categoryStyles = {
  stability: {
    border: "border-l-info",
    icon: "bg-info/15 text-info",
  },
  performance: {
    border: "border-l-success",
    icon: "bg-success/15 text-success",
  },
  logs: {
    border: "border-l-secondary",
    icon: "bg-secondary/20 text-secondary",
  },
  security: {
    border: "border-l-error",
    icon: "bg-error/15 text-error",
  },
};

const categoryDescriptions = {
  stability: "Detect and respond to container stability issues",
  performance: "Monitor resource usage and performance metrics",
  logs: "Analyze log patterns and error conditions",
  security: "Identify security threats and suspicious activity"
};

export default function RuleTemplates({ rules, containers, groups, onTemplateActivated }: RuleTemplatesProps) {
  const [templates, setTemplates] = useState<TemplatesByCategory>({});
  const [availableMetrics, setAvailableMetrics] = useState<AvailableMetrics | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeCategory, setActiveCategory] = useState<string>('stability');
  const [selectedTemplate, setSelectedTemplate] = useState<RuleTemplate | null>(null);
  const [showActivationModal, setShowActivationModal] = useState(false);
  const [activatingTemplateId, setActivatingTemplateId] = useState<string | null>(null);

  useEffect(() => {
    loadTemplatesAndMetrics();
  }, []);

  const activeTemplateIds = useMemo(() => {
    const ids = new Set<string>();

    for (const rule of rules) {
      if (rule.template_source) {
        ids.add(rule.template_source);
      }
    }

    return ids;
  }, [rules]);

  const loadTemplatesAndMetrics = async () => {
    try {
      const [templatesResult, metricsResult] = await Promise.allSettled([
        apiService.getRuleTemplates(),
        apiService.getAvailableMetrics()
      ]);

      if (templatesResult.status === 'fulfilled') {
        setTemplates(templatesResult.value);
        const categories = Object.keys(templatesResult.value);
        if (categories.length > 0) {
          setActiveCategory(categories[0]);
        }
      }

      if (metricsResult.status === 'fulfilled') {
        setAvailableMetrics(metricsResult.value);
      }
    } catch (error) {
      console.error('Failed to load templates:', error);
    } finally {
      setLoading(false);
    }
  };

  const canActivateTemplate = (template: RuleTemplate): boolean => {
    if (!availableMetrics || !template.required_metrics.length) {
      return true; // No metrics required or metrics not loaded yet
    }

    return template.required_metrics.every(metric =>
      availableMetrics.available_metrics.includes(metric)
    );
  };

  const getMissingMetrics = (template: RuleTemplate): string[] => {
    if (!availableMetrics || !template.required_metrics.length) {
      return [];
    }

    return template.required_metrics.filter(metric =>
      !availableMetrics.available_metrics.includes(metric)
    );
  };

  const handleActivateTemplate = (template: RuleTemplate) => {
    if (activeTemplateIds.has(template.id)) {
      return;
    }

    setActivatingTemplateId(template.id);
    setSelectedTemplate(template);
    setShowActivationModal(true);
  };

  const renderTemplateCard = (template: RuleTemplate) => {
    const canActivate = canActivateTemplate(template);
    const missingMetrics = getMissingMetrics(template);
    const Icon = categoryIcons[template.category as keyof typeof categoryIcons];
    const categoryStyle = categoryStyles[template.category as keyof typeof categoryStyles] ?? categoryStyles.stability;
    const isTemplateActive = activeTemplateIds.has(template.id);
    const isTemplateActivating = activatingTemplateId === template.id;

    return (
      <Card key={template.id} className={`p-6 hover:shadow-lg transition-all duration-200 border-l-4 ${categoryStyle.border}`}>
        <div className="flex items-start justify-between">
          <div className="flex items-start space-x-3 flex-1">
            <div className={`p-2 rounded-lg ${categoryStyle.icon}`}>
              <Icon className="w-5 h-5" />
            </div>
            <div className="flex-1">
              <h3 className="text-lg font-semibold text-text mb-2">{template.name}</h3>
              <p className="text-neutral-text text-sm leading-relaxed mb-4">{template.description}</p>

              {/* Template details */}
              <div className="space-y-2 mb-4">
                {template.timeline_minutes && (
                  <div className="flex items-center text-sm text-neutral-text">
                    <Clock className="w-4 h-4 mr-2" />
                    Time window: {template.timeline_minutes} minutes
                  </div>
                )}
                {template.timeline_count && (
                  <div className="flex items-center text-sm text-neutral-text">
                    <Hash className="w-4 h-4 mr-2" />
                    Threshold: {template.timeline_count} occurrences
                  </div>
                )}
                {template.actions.length > 0 && (
                  <div className="flex items-center text-sm text-neutral-text">
                    <Settings className="w-4 h-4 mr-2" />
                    Actions: {template.actions.map(a => a.type).join(', ')}
                  </div>
                )}
              </div>

              {/* Requirements note: metrics */}
              {template.required_metrics.length > 0 && (
                <div className="mb-4">
                  <div className="text-xs text-neutral-text mb-1">Required metrics:</div>
                  <div className="flex flex-wrap gap-1">
                    {template.required_metrics.map(metric => (
                      <span key={metric} className={`px-2 py-1 rounded text-xs ${
                        availableMetrics?.available_metrics.includes(metric)
                          ? 'bg-success/15 text-success'
                          : 'bg-error/15 text-error'
                      }`}>
                        {metric}
                        {availableMetrics?.available_metrics.includes(metric) ?
                          <CheckCircle className="w-3 h-3 ml-1 inline" /> :
                          <AlertCircle className="w-3 h-3 ml-1 inline" />
                        }
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>

          <div className="ml-4">
            {canActivate ? (
              <div className="flex flex-col items-end gap-1">
                <Button
                  onClick={() => handleActivateTemplate(template)}
                  className={`flex items-center ${isTemplateActive ? 'opacity-60 cursor-not-allowed' : ''}`}
                  disabled={isTemplateActivating || isTemplateActive}
                >
                  <Play className="w-4 h-4 mr-2" />
                  {isTemplateActivating ? 'Activating...' : isTemplateActive ? 'Activated' : 'Activate'}
                </Button>
                {isTemplateActive && (
                  <span className="text-xs font-medium text-warning">Already active</span>
                )}
              </div>
            ) : (
              <div className="relative">
                <Button
                  disabled
                  className="flex items-center opacity-50 cursor-not-allowed"
                  title={`Missing required metrics: ${missingMetrics.join(', ')}`}
                >
                  <AlertCircle className="w-4 h-4 mr-2" />
                  Unavailable
                </Button>
              </div>
            )}
          </div>
        </div>
      </Card>
    );
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="w-8 h-8 border-4 border-primary/30 border-t-transparent rounded-full animate-spin mx-auto mb-4"></div>
          <p className="text-neutral-text">Loading templates...</p>
        </div>
      </div>
    );
  }

  const categories = Object.keys(templates);
  if (categories.length === 0) {
    return (
      <div className="text-center py-12">
        <Info className="w-16 h-16 text-neutral-text mx-auto mb-4" />
        <h3 className="text-lg font-semibold text-text mb-2">No Templates Available</h3>
        <p className="text-neutral-text">Rule templates are not configured.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h2 className="text-2xl font-bold text-text mb-2">Rule Templates</h2>
        <p className="text-neutral-text">
          Quick-start templates for common monitoring scenarios. Activate and customize to your needs.
        </p>
      </div>

      {/* Category tabs */}
      <div className="border-b border-divider dark:border-divider">
        <nav className="flex space-x-8">
          {categories.map(category => {
            const Icon = categoryIcons[category as keyof typeof categoryIcons];
            const isActive = category === activeCategory;

            return (
              <button
                key={category}
                onClick={() => setActiveCategory(category)}
                className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  isActive
                    ? 'border-primary/30 text-info'
                    : 'border-transparent text-neutral-text hover:text-text hover:border-divider'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span className="capitalize">{category}</span>
                <span className="bg-neutral/20 text-neutral-text dark:bg-alt-foreground dark:text-text text-xs px-2 py-0.5 rounded-full">
                  {templates[category]?.length || 0}
                </span>
              </button>
            );
          })}
        </nav>
      </div>

      {/* Category description */}
      {categoryDescriptions[activeCategory as keyof typeof categoryDescriptions] && (
        <div className="bg-foreground/70 dark:bg-foreground/60 rounded-lg p-4">
          <p className="text-text dark:text-text text-sm">
            {categoryDescriptions[activeCategory as keyof typeof categoryDescriptions]}
          </p>
        </div>
      )}

      {/* Templates grid */}
      <div className="space-y-4">
        {templates[activeCategory]?.map(renderTemplateCard) || (
          <div className="text-center py-8 text-neutral-text">
            No templates available in this category.
          </div>
        )}
      </div>

      {/* Template Activation Modal */}
      {selectedTemplate && (
        <TemplateActivationModal
          template={selectedTemplate}
          containers={containers}
          groups={groups}
          isOpen={showActivationModal}
          onClose={() => {
            setShowActivationModal(false);
            setSelectedTemplate(null);
            setActivatingTemplateId(null);
          }}
          onActivated={async () => {
            setShowActivationModal(false);

            try {
              await onTemplateActivated();
            } finally {
              setSelectedTemplate(null);
              setActivatingTemplateId(null);
            }
          }}
        />
      )}
    </div>
  );
}

// Template Activation Modal Component
interface TemplateActivationModalProps {
  template: RuleTemplate;
  containers: ContainerInfo[];
  groups: GroupInfo[];
  isOpen: boolean;
  onClose: () => void;
  onActivated: () => Promise<void> | void;
}

const buildContainerKey = (container: { name: string; host_id?: string }) => {
  const hostId = container.host_id || 'local';
  return `${hostId}:${container.name}`;
};

function TemplateActivationModal({
  template,
  containers,
  groups,
  isOpen,
  onClose,
  onActivated
}: TemplateActivationModalProps) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Templates: lock down name and settings; only allow choosing scope
  const [ruleName] = useState(template.name);
  const [selectedHost, setSelectedHost] = useState<string>('');
  const [scopeMode, setScopeMode] = useState<'all' | 'specific'>('all');
  const [selectedContainers, setSelectedContainers] = useState<string[]>([]);
  const [selectedGroups, setSelectedGroups] = useState<string[]>([]);
  const [containerSearch, setContainerSearch] = useState('');
  const [customizations] = useState<Record<string, any>>(() => {
    // Initialize with default values from template
    const defaults: Record<string, any> = {};
    if (template.customizable_fields) {
      template.customizable_fields.forEach(field => {
        if (field === 'timeline_minutes' && template.timeline_minutes) {
          defaults[field] = template.timeline_minutes;
        } else if (field === 'timeline_count' && template.timeline_count) {
          defaults[field] = template.timeline_count;
        } else if (field === 'trigger_value' && template.trigger_value) {
          defaults[field] = typeof template.trigger_value === 'string' ? template.trigger_value : '';
        } else if (field.startsWith('trigger_value.') && typeof template.trigger_value === 'object') {
          const key = field.split('.')[1];
          if (template.trigger_value[key] !== undefined) {
            defaults[field] = template.trigger_value[key];
          }
        }
      });
    }
    return defaults;
  });

  // Duplicate detection state
  const [showDuplicateDialog, setShowDuplicateDialog] = useState(false);
  const [duplicateRule, setDuplicateRule] = useState<AlertRule | null>(null);
  const [pendingActivation, setPendingActivation] = useState<any>(null);

  // Host options derived from containers
  const hostOptions = useMemo(() => {
    const uniqueHosts = new Map<string, { containerCount: number }>();
    for (const container of containers) {
      const hostId = container.host_id || 'local';
      const existing = uniqueHosts.get(hostId);
      if (existing) {
        existing.containerCount++;
      } else {
        uniqueHosts.set(hostId, { containerCount: 1 });
      }
    }
    return Array.from(uniqueHosts.entries()).map(([hostId, data]) => ({
      value: hostId,
      label: `${hostId} (${data.containerCount} containers)`,
    }));
  }, [containers]);

  // Containers filtered by selected host
  const filteredContainerOptions = useMemo(() => {
    if (!selectedHost) return [];
    return containers
      .filter(c => (c.host_id || 'local') === selectedHost)
      .filter(c => !containerSearch || c.name.toLowerCase().includes(containerSearch.toLowerCase()))
      .map(c => ({ value: buildContainerKey(c), label: c.name }));
  }, [containers, selectedHost, containerSearch]);

  const handleActivate = async () => {
    // Validate host selection
    if (!selectedHost) {
      setError('Please select a host before activating.');
      return;
    }

    setLoading(true);
    setError(null);

    try {
      const scopeType = scopeMode === 'all' ? 'herald' as const : 'container' as const;
      const scopeTargets = scopeMode === 'all' ? [selectedHost] : selectedContainers;

      const activation = {
        rule_name: ruleName,
        // Note: Do not allow editing template parameters; send defaults only
        customizations,
        scope_type: scopeType,
        scope_targets: scopeTargets
      };

      // Check for duplicates first
      const duplicateCheck = await apiService.checkDuplicateRule(template.id, activation);

      if (duplicateCheck.is_duplicate && duplicateCheck.similar_rule) {
        // Show duplicate dialog
        setDuplicateRule(duplicateCheck.similar_rule);
        setPendingActivation(activation);
        setShowDuplicateDialog(true);
        setLoading(false);
        return;
      }

      // No duplicates, proceed with activation
      await apiService.activateTemplate(template.id, activation);
      await onActivated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to activate template');
    } finally {
      setLoading(false);
    }
  };

  const handleCreateAnyway = async () => {
    if (!pendingActivation) return;

    setShowDuplicateDialog(false);
    setLoading(true);
    setError(null);

    try {
      await apiService.activateTemplate(template.id, pendingActivation);
      await onActivated();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to activate template');
    } finally {
      setLoading(false);
      setPendingActivation(null);
      setDuplicateRule(null);
    }
  };

  const handleModifySettings = () => {
    setShowDuplicateDialog(false);
    // Keep the dialog open so user can modify settings
    setPendingActivation(null);
    setDuplicateRule(null);
  };

  const handleCloseDuplicateDialog = () => {
    setShowDuplicateDialog(false);
    setPendingActivation(null);
    setDuplicateRule(null);
  };
  return (
    <Modal isOpen={isOpen} onClose={onClose} title={`Activate: ${template.name}`}>
      <div className="space-y-6">
        {error && (
          <div className="bg-error/10 border border-error/30 rounded-md p-4">
            <div className="flex">
              <AlertCircle className="h-5 w-5 text-error" />
              <div className="ml-3">
                <h3 className="text-sm font-medium text-error">Error</h3>
                <p className="text-sm text-error mt-1">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Rule Name (read-only for templates) */}
        <div>
          <label className="block text-sm font-medium text-text mb-2">
            Rule Name
          </label>
          <input
            type="text"
            value={ruleName}
            readOnly
            disabled
            className="w-full px-3 py-2 border border-divider rounded-md bg-foreground/70 text-neutral-text cursor-not-allowed"
            placeholder="Template rule name"
          />
        </div>

        {/* Host Selection */}
        <div>
          <label className="block text-sm font-medium text-text mb-2">
            Select Host
          </label>
          <select
            value={selectedHost}
            disabled={hostOptions.length === 0}
            onChange={(e) => {
              setSelectedHost(e.target.value);
              setSelectedContainers([]);
              setContainerSearch('');
            }}
            className="w-full px-3 py-2 border border-divider rounded-md text-sm focus:ring-primary/40 focus:border-primary bg-background"
          >
            <option value="">
              {hostOptions.length === 0 ? 'No monitored containers' : '-- Choose a host --'}
            </option>
            {hostOptions.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </select>
        </div>

        {/* Scope Mode Toggle */}
        {selectedHost && (
          <div>
            <label className="block text-sm font-medium text-text mb-2">
              Apply Rule To
            </label>
            <div className="flex rounded-md overflow-hidden border border-divider">
              <button
                type="button"
                onClick={() => setScopeMode('all')}
                className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                  scopeMode === 'all'
                    ? 'bg-info text-info-950'
                    : 'bg-background text-text hover:bg-foreground/70'
                }`}
              >
                All containers
              </button>
              <button
                type="button"
                onClick={() => setScopeMode('specific')}
                className={`flex-1 px-4 py-2 text-sm font-medium transition-colors ${
                  scopeMode === 'specific'
                    ? 'bg-info text-info-950'
                    : 'bg-background text-text hover:bg-foreground/70'
                }`}
              >
                Specific containers
              </button>
            </div>
          </div>
        )}

        {/* Container Selection (when specific mode) */}
        {selectedHost && scopeMode === 'specific' && (
          <div>
            <label className="block text-sm font-medium text-text mb-2">
              Select Containers on {selectedHost}
            </label>
            <input
              type="text"
              placeholder="Search containers..."
              value={containerSearch}
              onChange={(e) => setContainerSearch(e.target.value)}
              className="w-full px-3 py-2 mb-2 border border-divider rounded-md text-sm focus:ring-primary/40 focus:border-primary"
            />
            <MultiSelect
              options={filteredContainerOptions}
              value={selectedContainers}
              onChange={setSelectedContainers}
              placeholder="Choose containers..."
            />
          </div>
        )}

        {/* Customization Fields (disabled for templates) */}
        {template.customizable_fields && template.customizable_fields.length > 0 && (
          <div className="opacity-60 pointer-events-none">
            <h3 className="text-lg font-medium text-text mb-4">Customize Settings (locked for templates)</h3>
            <div className="space-y-4">
              {template.customizable_fields.map((field) => (
                <div key={field} className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-semibold text-neutral-text mb-2">{field}</label>
                    <input
                      className="w-full px-3 py-2 border border-divider rounded-md bg-foreground/70 text-neutral-text"
                      value={
                        (field === 'timeline_minutes' && (template.timeline_minutes ?? '')) ||
                        (field === 'timeline_count' && (template.timeline_count ?? '')) ||
                        (field === 'trigger_value' && (typeof template.trigger_value === 'string' ? template.trigger_value : '')) ||
                        ''
                      }
                      readOnly
                      disabled
                    />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex justify-end space-x-3 pt-6 border-t border-divider">
          <Button variant="outline" onClick={onClose} disabled={loading}>
            Cancel
          </Button>
          <Button onClick={handleActivate} loading={loading}>
            Activate Rule
          </Button>
        </div>
      </div>

      {/* Duplicate Detection Dialog */}
      {showDuplicateDialog && duplicateRule && pendingActivation && (
        <DuplicateRuleDialog
          isOpen={showDuplicateDialog}
          onClose={handleCloseDuplicateDialog}
          onCreateAnyway={handleCreateAnyway}
          onModifySettings={handleModifySettings}
          existingRule={duplicateRule}
          newRuleData={{
            name: pendingActivation.rule_name,
            trigger_type: template.trigger_type as 'keyword' | 'metric_threshold' | 'container_event',
            trigger_value: template.trigger_value,
            timeline_minutes: template.timeline_minutes,
            timeline_count: template.timeline_count,
            actions: template.actions.map((action: any) => ({
              type: action.type as 'notification' | 'restart_container' | 'kill_container' | 'stop_container' | 'start_container',
              config: action.config,
              delay_seconds: action.delay_seconds
            })),
            scope_type: pendingActivation.scope_type,
            scope_targets: pendingActivation.scope_targets,
            tags: pendingActivation.custom_tags || [],
            enabled: true
          }}
          templateName={template.name}
        />
      )}
    </Modal>
  );
}
