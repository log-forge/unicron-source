/**
 * useDragResize Hook
 *
 * Provides drag-to-resize functionality for elements.
 * Supports both vertical and horizontal resizing with constraints.
 */

import { useRef, useState, useCallback, useEffect } from "react";

interface DragResizeOptions {
  initHeight?: number;
  initWidth?: number;
  opts?: {
    axis?: "x" | "y" | "both";
    minHeight?: number;
    maxHeight?: number;
    minWidth?: number;
    maxWidth?: number;
    invertY?: boolean;
    invertX?: boolean;
    onResize?: (width: number, height: number) => void;
  };
}

interface DragResizeResult {
  ref: React.RefObject<HTMLElement | null>;
  size: { width: number; height: number };
  resizeHandleProps: {
    onMouseDown: (e: React.MouseEvent) => void;
  };
}

export function useDragResize(options: DragResizeOptions = {}): DragResizeResult {
  const {
    initHeight = 300,
    initWidth = 400,
    opts = {},
  } = options;

  const {
    axis = "y",
    minHeight = 100,
    maxHeight = 800,
    minWidth = 200,
    maxWidth = 1200,
    invertY = false,
    invertX = false,
    onResize,
  } = opts;

  const ref = useRef<HTMLElement | null>(null);
  const [size, setSize] = useState({ width: initWidth, height: initHeight });
  const isDragging = useRef(false);
  const startPos = useRef({ x: 0, y: 0 });
  const startSize = useRef({ width: initWidth, height: initHeight });

  const handleMouseMove = useCallback(
    (e: MouseEvent) => {
      if (!isDragging.current) return;

      let newWidth = size.width;
      let newHeight = size.height;

      if (axis === "x" || axis === "both") {
        const deltaX = invertX
          ? startPos.current.x - e.clientX
          : e.clientX - startPos.current.x;
        newWidth = Math.min(
          maxWidth,
          Math.max(minWidth, startSize.current.width + deltaX)
        );
      }

      if (axis === "y" || axis === "both") {
        const deltaY = invertY
          ? startPos.current.y - e.clientY
          : e.clientY - startPos.current.y;
        newHeight = Math.min(
          maxHeight,
          Math.max(minHeight, startSize.current.height + deltaY)
        );
      }

      setSize({ width: newWidth, height: newHeight });
      onResize?.(newWidth, newHeight);
    },
    [axis, invertX, invertY, maxHeight, maxWidth, minHeight, minWidth, onResize, size.height, size.width]
  );

  const handleMouseUp = useCallback(() => {
    isDragging.current = false;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);

    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [handleMouseMove, handleMouseUp]);

  const handleMouseDown = useCallback(
    (e: React.MouseEvent) => {
      e.preventDefault();
      isDragging.current = true;
      startPos.current = { x: e.clientX, y: e.clientY };
      startSize.current = { ...size };
      document.body.style.cursor = axis === "y" ? "ns-resize" : axis === "x" ? "ew-resize" : "nwse-resize";
      document.body.style.userSelect = "none";
    },
    [axis, size]
  );

  return {
    ref,
    size,
    resizeHandleProps: {
      onMouseDown: handleMouseDown,
    },
  };
}
