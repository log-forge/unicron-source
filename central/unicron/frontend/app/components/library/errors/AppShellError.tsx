import { isAxiosError } from "axios";
import { AlertCircle } from "lucide-react";
import { useNavigate } from "react-router";
import { signOut } from "../../../utils/auth/auth-client";
import { Button } from "../buttons/Button";

interface AppShellErrorProps {
  error?: Error | null;
  title?: string;
  message?: string;
  showRetry?: boolean;
  showSignIn?: boolean;
  onRetry?: () => void;
}

function getErrorInfo(error: Error | null | undefined): { title: string; message: string; isAuthError: boolean } {
  if (!error) {
    return {
      title: "Something went wrong",
      message: "An unexpected error occurred. Please try again.",
      isAuthError: false,
    };
  }

  if (isAxiosError(error)) {
    const status = error.response?.status;

    if (status === 401) {
      return {
        title: "Authentication Required",
        message: "Your session has expired or you need to sign in to access this page.",
        isAuthError: true,
      };
    }

    if (status === 403) {
      return {
        title: "Access Denied",
        message: "You don't have permission to access this resource. Please contact your administrator.",
        isAuthError: true,
      };
    }

    if (status === 503 || status === 502) {
      return {
        title: "Service Unavailable",
        message: "The service is temporarily unavailable. Please try again in a few moments.",
        isAuthError: false,
      };
    }
  }

  return {
    title: "Error Loading Data",
    message: error.message || "Failed to load the required data. Please try again.",
    isAuthError: false,
  };
}

export function AppShellError({ error, title, message, showRetry = true, showSignIn, onRetry }: AppShellErrorProps) {
  const navigate = useNavigate();
  const errorInfo = getErrorInfo(error);

  const displayTitle = title ?? errorInfo.title;
  const displayMessage = message ?? errorInfo.message;
  const shouldShowSignIn = showSignIn ?? errorInfo.isAuthError;

  const handleSignIn = async () => {
    const currentPath = typeof window !== "undefined" ? window.location.pathname : "/";
    // Sign out first to clear any stale credentials
    await signOut();
    navigate(`/sign-in?returnTo=${encodeURIComponent(currentPath)}`);
  };

  const handleRetry = () => {
    if (onRetry) {
      onRetry();
    } else {
      window.location.reload();
    }
  };

  return (
    <div className="flex min-h-[60vh] w-full items-center justify-center p-lg">
      <div className="flex w-full max-w-4xl items-center gap-sm text-left">
        <div className="flex h-16 w-16 shrink-0 items-center justify-center rounded-full bg-error/10">
          <AlertCircle className="h-8 w-8 text-error-text" strokeWidth={1.5} />
        </div>

        <div className="flex min-w-0 flex-1 flex-col gap-xs">
          <div className="flex min-w-0 items-baseline gap-sm">
            <h2 className="shrink-0 text-h5 font-semibold whitespace-nowrap text-text">{displayTitle}</h2>
            <p className="min-w-0 flex-1 text-sm text-neutral-text">{displayMessage}</p>
          </div>

          {(shouldShowSignIn || showRetry) && (
            <div className="flex flex-wrap gap-xs">
              {shouldShowSignIn && (
                <Button tone="primary" textSize="sm" onPress={handleSignIn}>
                  Sign In
                </Button>
              )}
              {showRetry && (
                <Button tone="secondary" textSize="sm" onPress={handleRetry}>
                  Try Again
                </Button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default AppShellError;
