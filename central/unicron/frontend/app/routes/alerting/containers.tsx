/**
 * Alerting Containers Page
 *
 * Container monitoring view within the alerting section.
 * Uses the ContainersTable component and useContainers hook from alert-engine feature.
 */

import {
  useContainers,
  ContainersTable,
  LoadingSpinner,
} from "~/features/alert-engine";

// ============================================================================
// Component
// ============================================================================

export default function AlertingContainers() {
  const { containers, groups, loading, error, wsConnected } = useContainers();

  if (loading && containers.length === 0) {
    return <LoadingSpinner text="Loading containers..." />;
  }

  if (error) {
    return (
      <div className="p-4 bg-error/10 dark:bg-error/20 border border-error/30 dark:border-error/30 rounded-lg">
        <p className="text-error dark:text-error">Error loading containers: {error}</p>
      </div>
    );
  }

  return (
    <div>
      <div className="flex justify-between items-center mb-6">
        <h2 className="text-2xl font-bold text-text dark:text-text">
          Containers
        </h2>
        {wsConnected && (
          <span className="inline-flex items-center px-2.5 py-1 text-xs font-medium bg-success/10 text-success dark:bg-success/50 dark:text-success rounded-full">
            <span className="w-2 h-2 mr-1.5 bg-success rounded-full animate-pulse"></span>
            Live
          </span>
        )}
      </div>
      <ContainersTable containers={containers} groups={groups} />
    </div>
  );
}
