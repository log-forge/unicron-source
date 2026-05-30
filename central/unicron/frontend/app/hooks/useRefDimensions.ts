/**
 * useRefDimensions Hook
 *
 * Tracks the dimensions of an element using ResizeObserver.
 * Returns a ref to attach to the element and the current dimensions.
 */

import { useRef, useState, useEffect } from "react";

export function useRefDimensions<T extends HTMLElement>(
  onResize?: () => void
): [React.RefObject<T | null>, { width: number; height: number }] {
  const ref = useRef<T | null>(null);
  const [dimensions, setDimensions] = useState({ width: 0, height: 0 });

  useEffect(() => {
    if (!ref.current) return;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDimensions({ width, height });
        onResize?.();
      }
    });

    observer.observe(ref.current);
    return () => observer.disconnect();
  }, [onResize]);

  return [ref, dimensions];
}
