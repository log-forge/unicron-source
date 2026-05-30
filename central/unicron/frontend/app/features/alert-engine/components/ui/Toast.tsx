import React from 'react';
import { createPortal } from 'react-dom';
import { AlertCircle, CheckCircle2, Info, X } from 'lucide-react';

interface ToastProps {
  message: string;
  variant?: 'success' | 'error' | 'info';
  onClose?: () => void;
  position?: 'bottom-center' | 'bottom-right';
}

export const Toast: React.FC<ToastProps> = ({
  message,
  variant = 'info',
  onClose,
  position = 'bottom-center',
}) => {
  if (typeof document === 'undefined') {
    return null;
  }

  const styles = {
    success: {
      container: 'bg-success text-success-950',
      icon: CheckCircle2,
    },
    error: {
      container: 'bg-error text-error-950',
      icon: AlertCircle,
    },
    info: {
      container: 'bg-info text-info-950',
      icon: Info,
    },
  } as const;

  const positions = {
    'bottom-center': 'bottom-4 left-1/2 -translate-x-1/2',
    'bottom-right': 'bottom-4 right-4',
  } as const;
  const { container, icon: Icon } = styles[variant];

  const node = (
    <div className={`fixed z-60 pointer-events-none ${positions[position]}`}>
      <div
        className={`
          pointer-events-auto flex max-w-[min(24rem,calc(100vw-2rem))] items-start gap-3
          rounded-lg px-4 py-3 shadow-lg ring-1 ring-divider
          ${container}
        `}
      >
        <Icon className="mt-0.5 h-5 w-5 shrink-0" />
        <p className="min-w-0 flex-1 break-words text-sm font-medium leading-5">
          {message}
        </p>
        {onClose && (
          <button
            type="button"
            onClick={onClose}
            className="shrink-0 rounded p-0.5 text-background/75 transition-colors hover:text-background"
            aria-label="Dismiss notification"
          >
            <X className="h-4 w-4" />
          </button>
        )}
      </div>
    </div>
  );

  return createPortal(node, document.body);
};

export default Toast;
