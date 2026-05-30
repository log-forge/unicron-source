/**
 * FilesTab Component
 *
 * Two-panel file browser with collapsible sidebar and Monaco editor
 * for read-only file viewing with syntax highlighting.
 */

import { useState, Suspense, lazy, useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { PanelLeft, PanelLeftClose, File, AlertCircle } from "lucide-react";
import { ExplorerPanel } from "~/components/explorer";
import { getContainerFile, closeFileConnection } from "~/utils/api/files";
import { detectMonacoLanguage } from "~/constants/monacoLanguages";

// Lazy load Monaco editor for performance
const Editor = lazy(() => import("@monaco-editor/react").then((m) => ({ default: m.Editor })));

// ============================================================================
// Types
// ============================================================================

interface FilesTabProps {
  containerKey: string;
  hostId: string | null;
}

// ============================================================================
// Helpers
// ============================================================================

function formatFileSize(bytes: number): string {
  if (bytes >= 1024 * 1024) {
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  }
  if (bytes >= 1024) {
    return `${(bytes / 1024).toFixed(2)} KB`;
  }
  return "<1 KB";
}

function getFileName(path: string): string {
  return path.split("/").pop() || path;
}

// ============================================================================
// Component
// ============================================================================

export default function FilesTab({ containerKey, hostId }: FilesTabProps) {
  const [isSidePanelOpen, setIsSidePanelOpen] = useState(true);
  const [currentPath, setCurrentPath] = useState("/");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [expandedDirs, setExpandedDirs] = useState<Record<string, boolean>>({});

  // Cleanup WebSocket connection on unmount
  useEffect(() => {
    return () => {
      closeFileConnection();
    };
  }, []);

  // Detect dark mode
  const isDark = typeof document !== "undefined" &&
    document.documentElement.getAttribute("data-theme") === "dark";

  // Fetch file content when a file is selected
  const {
    data: fileData,
    isPending: isLoadingFile,
    isError: isFileError,
    error: fileError,
  } = useQuery({
    queryKey: ["file", containerKey, selectedFile, hostId],
    queryFn: () => getContainerFile(containerKey, selectedFile!, hostId),
    enabled: !!selectedFile,
    staleTime: 30 * 1000, // Cache for 30 seconds
  });

  return (
    <div className="grid h-[600px] grid-cols-[auto_1fr] gap-0">
      {/* Left panel: File tree */}
      <div
        className={`border-r border-neutral/20 transition-all duration-200 ${
          isSidePanelOpen ? "w-[260px]" : "w-0"
        } overflow-hidden`}
      >
        {isSidePanelOpen && (
          <ExplorerPanel
            containerKey={containerKey}
            currentPath={currentPath}
            setCurrentPath={setCurrentPath}
            selectedFile={selectedFile}
            setSelectedFile={setSelectedFile}
            expandedDirs={expandedDirs}
            setExpandedDirs={setExpandedDirs}
            hostId={hostId}
          />
        )}
      </div>

      {/* Right panel: Monaco editor */}
      <div className="flex flex-col overflow-hidden">
        {/* Header bar */}
        <div className="flex shrink-0 items-center gap-sm border-b border-neutral/20 px-sm py-xs">
          {/* Toggle button */}
          <button
            type="button"
            onClick={() => setIsSidePanelOpen(!isSidePanelOpen)}
            className="rounded p-2xs text-neutral transition-colors hover:bg-neutral/10 hover:text-text"
            title={isSidePanelOpen ? "Hide file tree" : "Show file tree"}
          >
            {isSidePanelOpen ? (
              <PanelLeftClose className="h-5 w-5" />
            ) : (
              <PanelLeft className="h-5 w-5" />
            )}
          </button>

          {/* File name and size */}
          {selectedFile ? (
            <div className="flex items-center gap-xs overflow-hidden">
              <File className="h-4 w-4 shrink-0 text-neutral" />
              <span className="truncate text-sm font-medium text-text">
                {getFileName(selectedFile)}
              </span>
              {fileData && (
                <span className="shrink-0 text-xs text-neutral">
                  ({formatFileSize(fileData.size)})
                </span>
              )}
            </div>
          ) : (
            <span className="text-sm text-neutral">No file selected</span>
          )}
        </div>

        {/* Editor area */}
        <div className="flex-1 overflow-hidden">
          {!selectedFile ? (
            // No file selected placeholder
            <div className="flex h-full flex-col items-center justify-center text-center">
              <File className="mb-sm h-12 w-12 text-neutral/50" />
              <p className="text-sm text-neutral">
                Select a file from the explorer to view its contents
              </p>
            </div>
          ) : isLoadingFile ? (
            // Loading state
            <div className="flex h-full flex-col items-center justify-center">
              <div className="h-8 w-8 animate-spin rounded-full border-2 border-neutral/20 border-t-primary" />
              <p className="mt-sm text-sm text-neutral">Loading file...</p>
            </div>
          ) : isFileError ? (
            // Error state
            <div className="flex h-full flex-col items-center justify-center text-center">
              <AlertCircle className="mb-sm h-12 w-12 text-error" />
              <p className="text-sm font-medium text-error">Failed to load file</p>
              <p className="mt-2xs text-xs text-neutral">
                {fileError instanceof Error ? fileError.message : "Unknown error"}
              </p>
            </div>
          ) : (
            // Monaco editor
            <Suspense
              fallback={
                <div className="flex h-full items-center justify-center">
                  <p className="text-sm text-neutral">Loading editor...</p>
                </div>
              }
            >
              <Editor
                height="100%"
                language={detectMonacoLanguage(getFileName(selectedFile))}
                value={fileData?.content || ""}
                theme={isDark ? "vs-dark" : "light"}
                options={{
                  readOnly: true,
                  minimap: { enabled: false },
                  fontSize: 13,
                  lineNumbers: "on",
                  scrollBeyondLastLine: false,
                  wordWrap: "on",
                  automaticLayout: true,
                  domReadOnly: true,
                  contextmenu: false,
                  folding: true,
                  renderLineHighlight: "line",
                }}
              />
            </Suspense>
          )}
        </div>
      </div>
    </div>
  );
}
