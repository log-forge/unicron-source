/**
 * ExplorerPanel Component
 *
 * File explorer panel wrapping DirectoryTree with header and scrolling.
 * Supports both controlled (external state) and uncontrolled (internal state) modes.
 */

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getContainerDirectory, type Directory } from "~/utils/api/files";
import DirectoryTree from "./DirectoryTree";

// ============================================================================
// Types
// ============================================================================

interface ExplorerPanelProps {
  containerKey: string;
  initDirectory?: Directory;
  currentPath?: string;
  setCurrentPath?: (path: string) => void;
  selectedFile?: string | null;
  setSelectedFile?: (file: string | null) => void;
  expandedDirs?: Record<string, boolean>;
  setExpandedDirs?: (dirs: Record<string, boolean>) => void;
  hostId?: string | null;
}

// ============================================================================
// Component
// ============================================================================

export default function ExplorerPanel({
  containerKey,
  initDirectory,
  currentPath: externalCurrentPath,
  setCurrentPath: externalSetCurrentPath,
  selectedFile: externalSelectedFile,
  setSelectedFile: externalSetSelectedFile,
  expandedDirs: externalExpandedDirs,
  setExpandedDirs: externalSetExpandedDirs,
  hostId,
}: ExplorerPanelProps) {
  // Internal state (used when external state not provided)
  const [internalCurrentPath, setInternalCurrentPath] = useState("/");
  const [internalSelectedFile, setInternalSelectedFile] = useState<string | null>(null);
  const [internalExpandedDirs, setInternalExpandedDirs] = useState<Record<string, boolean>>({});

  // Use external state if provided, otherwise use internal
  const currentPath = externalCurrentPath ?? internalCurrentPath;
  const setCurrentPath = externalSetCurrentPath ?? setInternalCurrentPath;
  const selectedFile = externalSelectedFile ?? internalSelectedFile;
  const setSelectedFile = externalSetSelectedFile ?? setInternalSelectedFile;
  const expandedDirs = externalExpandedDirs ?? internalExpandedDirs;
  const setExpandedDirs = externalSetExpandedDirs ?? setInternalExpandedDirs;

  // Fetch root directory on mount if not provided
  const { data: rootDirectory, isLoading } = useQuery({
    queryKey: ["directory", containerKey, "/", hostId],
    queryFn: () => getContainerDirectory(containerKey, "/", hostId),
    enabled: !initDirectory,
    staleTime: 60 * 1000, // Cache for 1 minute
  });

  const directory = initDirectory || rootDirectory;

  // Filter out "." and ".." entries
  const filteredEntries = directory?.entries.filter(
    (entry) => entry.name !== "." && entry.name !== ".."
  );

  const toggleDirectory = (path: string) => {
    setExpandedDirs({
      ...expandedDirs,
      [path]: !expandedDirs[path],
    });
  };

  const handleFileSelect = (path: string) => {
    setSelectedFile(path);
  };

  if (isLoading) {
    return (
      <div className="flex h-full w-full flex-col overflow-hidden">
        <p className="shrink-0 px-sm py-xs font-bold text-text">Explorer</p>
        <div className="flex flex-1 items-center justify-center">
          <p className="text-sm text-neutral">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <div className="flex h-full w-full flex-col overflow-hidden">
      <p className="shrink-0 px-sm py-xs font-bold text-text">Explorer</p>
      <div className="flex-1 overflow-auto px-xs">
        {filteredEntries && filteredEntries.length > 0 ? (
          <DirectoryTree
            entries={filteredEntries}
            expandedDirs={expandedDirs}
            toggleDirectory={toggleDirectory}
            selectedFile={selectedFile}
            onFileSelect={handleFileSelect}
            containerKey={containerKey}
            level={0}
            parentPath="/"
            hostId={hostId}
          />
        ) : (
          <p className="py-md text-center text-sm text-neutral italic">
            No files found
          </p>
        )}
      </div>
    </div>
  );
}
