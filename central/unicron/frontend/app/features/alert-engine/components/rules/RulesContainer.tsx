import { useState } from "react";
import type { AlertRule, ContainerInfo, GroupInfo } from "../../types";
import UnifiedRulesList from "./UnifiedRulesList";
import RuleTemplates from "./RuleTemplates";
import { Shield, Layers, Settings } from "lucide-react";
import GatekeeperSettingsModal from "./GatekeeperSettingsModal";
import { Toast } from "../ui";

interface RulesContainerProps {
  rules: AlertRule[];
  containers: ContainerInfo[];
  groups: GroupInfo[];
  canManageRules: boolean;
  onDelete: (id: string) => void;
  onEdit: (rule: AlertRule) => void;
  onToggleEnabled: (id: string, enabled: boolean) => void;
  onBulkToggle?: (ruleIds: string[], enabled: boolean) => void;
  onCreateClick: () => void;
  onTemplateActivated: () => Promise<void> | void;
}

type TabType = 'all-rules' | 'templates';

export default function RulesContainer({
  rules,
  containers,
  groups,
  canManageRules,
  onDelete,
  onEdit,
  onToggleEnabled,
  onBulkToggle,
  onCreateClick,
  onTemplateActivated
}: RulesContainerProps) {
  const [activeTab, setActiveTab] = useState<TabType>('all-rules');
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [showSavedToast, setShowSavedToast] = useState(false);

  const tabs = [
    {
      id: 'all-rules' as TabType,
      name: 'All Rules',
      icon: Shield,
      count: rules.length
    },
    ...(canManageRules ? [{
      id: 'templates' as TabType,
      name: 'Templates',
      icon: Layers,
      count: null
    }] : [])
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h2 className="text-3xl font-bold text-text">Alert Rules</h2>
          {canManageRules && (
            <button
              className="ml-3 inline-flex items-center px-3 py-1.5 text-sm rounded bg-alt-foreground hover:bg-neutral/20 text-text"
              onClick={() => setShowAdvanced(true)}
              title="Configure advanced action guardrails"
            >
              <Settings className="w-4 h-4 mr-2" /> Advanced Settings
            </button>
          )}
        </div>
        <p className="text-neutral-text mt-1">
          {canManageRules ? 'Configure and manage your monitoring rules' : 'View-only access for alert rules'}
        </p>
      </div>

      {/* Sub-tabs */}
      <div className="border-b border-divider dark:border-divider">
        <nav className="flex space-x-8">
          {tabs.map(tab => {
            const Icon = tab.icon;
            const isActive = tab.id === activeTab;

            return (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex items-center space-x-2 py-4 px-1 border-b-2 font-medium text-sm transition-colors ${
                  isActive
                    ? 'border-primary/30 text-info'
                    : 'border-transparent text-neutral-text hover:text-text hover:border-divider'
                }`}
              >
                <Icon className="w-4 h-4" />
                <span>{tab.name}</span>
                {tab.count !== null && (
                  <span className="bg-neutral/20 text-neutral-text dark:bg-alt-foreground dark:text-text text-xs px-2 py-0.5 rounded-full">
                    {tab.count}
                  </span>
                )}
              </button>
            );
          })}
        </nav>
      </div>

      {/* Tab content */}
      <div>
        {activeTab === 'all-rules' && (
          <UnifiedRulesList
            rules={rules}
            onDelete={onDelete}
            onEdit={onEdit}
            onToggleEnabled={onToggleEnabled}
            onBulkToggle={onBulkToggle}
            onCreateClick={onCreateClick}
            showCreateButton={canManageRules}
            canManageRules={canManageRules}
          />
        )}

        {activeTab === 'templates' && canManageRules && (
          <RuleTemplates
            rules={rules}
            containers={containers}
            groups={groups}
            onTemplateActivated={onTemplateActivated}
          />
        )}
      </div>

      <GatekeeperSettingsModal
        isOpen={showAdvanced}
        onClose={() => setShowAdvanced(false)}
        onSaved={() => {
          setShowSavedToast(true);
          setTimeout(() => setShowSavedToast(false), 2000);
        }}
      />
      {showSavedToast && (
        <Toast variant="success" message="Advanced Settings Saved" />
      )}
    </div>
  );
}
