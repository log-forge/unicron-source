/**
 * DirectoryTree Component
 *
 * Recursive directory tree renderer for file exploration.
 * Supports lazy loading of subdirectories on expand.
 */

import { useQuery } from "@tanstack/react-query";
import { ChevronRight, ChevronDown, Folder, FolderOpen, File } from "lucide-react";
import { getContainerDirectory, type DirectoryEntry } from "~/utils/api/files";

// ============================================================================
// Types
// ============================================================================

interface DirectoryTreeProps {
  entries: DirectoryEntry[];
  expandedDirs: Record<string, boolean>;
  toggleDirectory: (path: string) => void;
  selectedFile: string | null;
  onFileSelect: (path: string) => void;
  containerKey: string;
  level: number;
  parentPath: string;
  hostId?: string | null;
}

// ============================================================================
// Component
// ============================================================================

export default function DirectoryTree({
  entries,
  expandedDirs,
  toggleDirectory,
  selectedFile,
  onFileSelect,
  containerKey,
  level,
  parentPath,
  hostId,
}: DirectoryTreeProps) {
  // Sort entries: directories first, then files, alphabetically within each group
  const sortedEntries = [...entries].sort((a, b) => {
    if (a.type !== b.type) {
      return a.type === "directory" ? -1 : 1;
    }
    return a.name.localeCompare(b.name);
  });

  return (
    <div className="flex flex-col">
      {sortedEntries.map((entry) => (
        <DirectoryTreeItem
          key={entry.path}
          entry={entry}
          expandedDirs={expandedDirs}
          toggleDirectory={toggleDirectory}
          selectedFile={selectedFile}
          onFileSelect={onFileSelect}
          containerKey={containerKey}
          level={level}
          hostId={hostId}
        />
      ))}
    </div>
  );
}

// ============================================================================
// Directory Tree Item
// ============================================================================

interface DirectoryTreeItemProps {
  entry: DirectoryEntry;
  expandedDirs: Record<string, boolean>;
  toggleDirectory: (path: string) => void;
  selectedFile: string | null;
  onFileSelect: (path: string) => void;
  containerKey: string;
  level: number;
  hostId?: string | null;
}

function DirectoryTreeItem({
  entry,
  expandedDirs,
  toggleDirectory,
  selectedFile,
  onFileSelect,
  containerKey,
  level,
  hostId,
}: DirectoryTreeItemProps) {
  const isExpanded = expandedDirs[entry.path] === true;
  const isSelected = selectedFile === entry.path;

  // Lazy load subdirectory contents when expanded
  const { data: subDir, isLoading: isLoadingSubDir } = useQuery({
    queryKey: ["directory", containerKey, entry.path, hostId],
    queryFn: () => getContainerDirectory(containerKey, entry.path, hostId),
    enabled: entry.type === "directory" && isExpanded,
    staleTime: 60 * 1000, // Cache for 1 minute
  });

  // Filter out "." and ".." entries
  const filteredSubEntries = subDir?.entries.filter(
    (e) => e.name !== "." && e.name !== ".."
  );

  const handleClick = () => {
    if (entry.type === "directory") {
      toggleDirectory(entry.path);
    } else {
      onFileSelect(entry.path);
    }
  };

  // Calculate padding based on nesting level
  const paddingLeft = level * 16;

  return (
    <div>
      {/* Entry row */}
      <button
        type="button"
        onClick={handleClick}
        className={`flex w-full items-center gap-2xs py-3xs text-left text-sm transition-colors hover:bg-neutral/10 ${
          isSelected ? "bg-primary/10 text-primary" : "text-text"
        }`}
        style={{ paddingLeft: `${paddingLeft}px` }}
      >
        {/* Chevron for directories */}
        {entry.type === "directory" ? (
          isExpanded ? (
            <ChevronDown className="h-4 w-4 shrink-0 text-neutral" />
          ) : (
            <ChevronRight className="h-4 w-4 shrink-0 text-neutral" />
          )
        ) : (
          <span className="w-4 shrink-0" /> // Spacer for alignment
        )}

        {/* Icon */}
        {entry.type === "directory" ? (
          isExpanded ? (
            <FolderOpen className="h-4 w-4 shrink-0 text-primary" />
          ) : (
            <Folder className="h-4 w-4 shrink-0 text-primary" />
          )
        ) : (
          <File className="h-4 w-4 shrink-0 text-neutral" />
        )}

        {/* Name */}
        <span className="truncate">{entry.name}</span>
      </button>

      {/* Subdirectory contents (lazy loaded) */}
      {entry.type === "directory" && isExpanded && (
        <div>
          {isLoadingSubDir ? (
            <div
              className="py-2xs text-xs text-neutral"
              style={{ paddingLeft: `${(level + 1) * 16 + 24}px` }}
            >
              Loading...
            </div>
          ) : filteredSubEntries && filteredSubEntries.length > 0 ? (
            <DirectoryTree
              entries={filteredSubEntries}
              expandedDirs={expandedDirs}
              toggleDirectory={toggleDirectory}
              selectedFile={selectedFile}
              onFileSelect={onFileSelect}
              containerKey={containerKey}
              level={level + 1}
              parentPath={entry.path}
              hostId={hostId}
            />
          ) : (
            <div
              className="py-2xs text-xs text-neutral italic"
              style={{ paddingLeft: `${(level + 1) * 16 + 24}px` }}
            >
              Empty directory
            </div>
          )}
        </div>
      )}
    </div>
  );
}
