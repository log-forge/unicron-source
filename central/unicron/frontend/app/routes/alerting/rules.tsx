/**
 * Alert Rules Page
 *
 * Ported from LogForge RulesPage.tsx
 * Provides alert rule management with CRUD operations.
 */

import { useState, useEffect } from 'react';
import { Plus } from 'lucide-react';
import {
  useRules,
  useContainers,
  RulesContainer,
  RuleBuilder,
  Modal,
  LoadingSpinner,
  Toast,
  Button,
} from '~/features/alert-engine';
import type { AlertRule } from '~/features/alert-engine';

export default function AlertRules() {
  const { rules, loading, createRule, updateRule, deleteRule, toggleRuleEnabled, bulkToggle, fetchRules } = useRules();
  const { containers, groups, loading: containersLoading } = useContainers();
  const [showRuleBuilder, setShowRuleBuilder] = useState(false);
  const [editingRule, setEditingRule] = useState<AlertRule | null>(null);
  const [ruleBuilderDraft, setRuleBuilderDraft] = useState<Partial<AlertRule> | null>(null);
  const [showSuccessToast, setShowSuccessToast] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');
  const [showErrorToast, setShowErrorToast] = useState(false);
  const [errorMessage, setErrorMessage] = useState('');
  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false);
  const [deletingRuleId, setDeletingRuleId] = useState<string | null>(null);
  const [deletingRuleName, setDeletingRuleName] = useState<string>('');
  const [isDeleting, setIsDeleting] = useState(false);

  // Auto-dismiss success toast after 3 seconds
  useEffect(() => {
    if (showSuccessToast) {
      const timer = setTimeout(() => {
        setShowSuccessToast(false);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [showSuccessToast]);

  // Auto-dismiss error toast after 5 seconds
  useEffect(() => {
    if (showErrorToast) {
      const timer = setTimeout(() => {
        setShowErrorToast(false);
      }, 5000);
      return () => clearTimeout(timer);
    }
  }, [showErrorToast]);

  const handleEdit = (rule: AlertRule) => {
    setRuleBuilderDraft(null);
    setEditingRule(rule);
    setShowRuleBuilder(true);
  };

  const openCreateRuleBuilder = () => {
    setEditingRule(null);
    setRuleBuilderDraft(null);
    setShowRuleBuilder(true);
  };

  const handleDelete = async (id: string) => {
    const rule = rules.find(r => r.id === id);
    setDeletingRuleId(id);
    setDeletingRuleName(rule?.name || 'this rule');
    setShowDeleteConfirm(true);
  };

  const confirmDelete = async () => {
    if (!deletingRuleId) return;

    setIsDeleting(true);
    try {
      await deleteRule(deletingRuleId);
      setShowDeleteConfirm(false);
      setDeletingRuleId(null);
      setDeletingRuleName('');
      setSuccessMessage('Rule deleted successfully');
      setShowSuccessToast(true);
    } catch (error) {
      console.error('Failed to delete rule:', error);
      setShowDeleteConfirm(false);
      setErrorMessage('Failed to delete rule');
      setShowErrorToast(true);
    } finally {
      setIsDeleting(false);
    }
  };

  const cancelDelete = () => {
    setShowDeleteConfirm(false);
    setDeletingRuleId(null);
    setDeletingRuleName('');
  };

  const handleSave = (ruleData: Omit<AlertRule, 'id'>) => {
    const editingSnapshot = editingRule;
    if (editingSnapshot) {
      const draftToRestore = { ...editingSnapshot, ...ruleData } as AlertRule;
      setRuleBuilderDraft(null);
      setShowRuleBuilder(false);
      setEditingRule(null);

      void (async () => {
        try {
          await updateRule(editingSnapshot.id, ruleData);
          setSuccessMessage('Rule updated successfully');
          setShowSuccessToast(true);
        } catch (error: unknown) {
          const err = error as { response?: { status?: number; data?: Record<string, unknown> }; message?: string };
          const errorMsg = err?.message || (err?.response?.data as any)?.message || 'Failed to save rule';
          setErrorMessage(errorMsg);
          setShowErrorToast(true);
          setEditingRule(draftToRestore);
          setShowRuleBuilder(true);
        }
      })();
      return;
    }

    const draftToRestore = { ...ruleData } as Partial<AlertRule>;
    setShowRuleBuilder(false);
    setEditingRule(null);
    setRuleBuilderDraft(null);

    void (async () => {
      try {
        await createRule(ruleData);
        setSuccessMessage('Rule created successfully');
        setRuleBuilderDraft(null);
        setShowSuccessToast(true);
      } catch (error: unknown) {
        const err = error as { response?: { status?: number; data?: Record<string, unknown> }; message?: string };
        const errorMsg = err?.message || (err?.response?.data as any)?.message || 'Failed to save rule';
        setErrorMessage(errorMsg);
        setShowErrorToast(true);
        setRuleBuilderDraft(draftToRestore);
        setShowRuleBuilder(true);
      }
    })();
  };

  const handleCancel = () => {
    setShowRuleBuilder(false);
    setEditingRule(null);
    setRuleBuilderDraft(null);
  };

  const handleToggleEnabled = async (id: string, enabled: boolean) => {
    try {
      await toggleRuleEnabled(id, enabled);
    } catch (error) {
      console.error('Failed to toggle rule:', error);
      setErrorMessage('Failed to toggle rule');
      setShowErrorToast(true);
    }
  };

  const handleBulkToggle = async (ruleIds: string[], enabled: boolean) => {
    try {
      await bulkToggle(ruleIds, enabled);
      setSuccessMessage(`Successfully ${enabled ? 'enabled' : 'disabled'} ${ruleIds.length} rule${ruleIds.length > 1 ? 's' : ''}`);
      setShowSuccessToast(true);
    } catch (error) {
      console.error('Failed to bulk toggle rules:', error);
      setErrorMessage('Failed to toggle rules');
      setShowErrorToast(true);
    }
  };

  const handleTemplateActivated = async () => {
    try {
      await fetchRules();
    } catch (error) {
      console.error('Failed to refresh rules after template activation:', error);
    }
    setSuccessMessage('Template activated successfully');
    setShowSuccessToast(true);
  };

  // Show loading only on first load (no cached data)
  if ((loading && rules.length === 0) || (containersLoading && containers.length === 0)) {
    return <LoadingSpinner text="Loading rules..." />;
  }

  return (
    <div>
      <RulesContainer
        rules={rules}
        containers={containers}
        groups={groups}
        canManageRules={true}
        onDelete={handleDelete}
        onEdit={handleEdit}
        onToggleEnabled={handleToggleEnabled}
        onBulkToggle={handleBulkToggle}
        onCreateClick={openCreateRuleBuilder}
        onTemplateActivated={handleTemplateActivated}
      />

      <Modal
        isOpen={showRuleBuilder}
        onClose={handleCancel}
        title={editingRule ? 'Edit Alert Rule' : 'Create Alert Rule'}
        panelClassName="max-w-7xl"
        bodyClassName="p-4 sm:p-5 lg:p-6"
      >
        <RuleBuilder
          onSave={handleSave}
          onCancel={handleCancel}
          initialRule={editingRule ?? ruleBuilderDraft}
        />
      </Modal>

      {/* Delete Confirmation Modal */}
      <Modal
        isOpen={showDeleteConfirm}
        onClose={cancelDelete}
        title="Delete Rule"
      >
        <div className="space-y-4">
          <p className="text-text">
            Are you sure you want to delete <strong>{deletingRuleName}</strong>?
          </p>
          <p className="text-sm text-neutral-text">
            This cannot be undone.
          </p>
          <div className="flex justify-end space-x-3 pt-4">
            <Button
              variant="secondary"
              onClick={cancelDelete}
              disabled={isDeleting}
            >
              Cancel
            </Button>
            <Button
              onClick={confirmDelete}
              disabled={isDeleting}
              className="bg-error hover:bg-error text-error-950"
            >
              {isDeleting ? 'Deleting...' : 'Delete'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* Success Toast */}
      {showSuccessToast && (
        <Toast variant="success" message={successMessage} />
      )}

      {/* Error Toast */}
      {showErrorToast && (
        <Toast variant="error" message={errorMessage} />
      )}
    </div>
  );
}
