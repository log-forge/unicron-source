import React, { useEffect } from "react";
import { createPortal } from "react-dom";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
  panelClassName?: string;
  bodyClassName?: string;
}

const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  title,
  children,
  panelClassName,
  bodyClassName,
}) => {
  // Prevent background scroll while modal is open
  useEffect(() => {
    if (!isOpen) return;
    const original = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = original || '';
    };
  }, [isOpen]);

  if (!isOpen) return null;
  if (typeof document === 'undefined') return null;

  const node = (
    <div className="fixed inset-0 z-50 animate-fade-in">
      <div className="fixed inset-0 bg-neutral-950/80 backdrop-blur-sm transition-opacity" onClick={onClose} />
      <div className="fixed inset-0 flex min-h-0 items-center justify-center p-2 pointer-events-none sm:p-4">
        <div
          className={`relative flex w-full min-w-0 min-h-0 max-h-[calc(100dvh-1rem)] flex-col overflow-hidden rounded-2xl bg-background shadow-2xl shadow-shadow/25 animate-scale-in pointer-events-auto sm:max-h-[calc(100dvh-2rem)] sm:rounded-3xl ${
            panelClassName || 'max-w-6xl'
          }`}
        >
          <div className="flex-shrink-0 glass-effect flex min-w-0 items-center justify-between gap-4 rounded-t-2xl border-b border-divider p-4 sm:rounded-t-3xl sm:p-6">
            <h3 className="min-w-0 truncate text-lg font-bold text-text sm:text-xl">{title}</h3>
            <button
              onClick={onClose}
              className="flex-shrink-0 rounded-xl p-2 text-neutral transition-all duration-200 hover:bg-foreground/10 hover:text-text"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
          <div className={`flex-1 min-h-0 min-w-0 overflow-y-auto overflow-x-hidden ${bodyClassName || 'p-4 sm:p-6'}`}>
            {children}
          </div>
        </div>
      </div>
    </div>
  );

  // Render to body to avoid clipping by transformed/scroll ancestors
  return createPortal(node, document.body);
};

export default Modal;
