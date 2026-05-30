import { data, Form, useActionData, useLoaderData, useNavigation } from "react-router";
import type { ActionFunctionArgs, LoaderFunctionArgs } from "react-router";
import { AuthenticityTokenInput } from "remix-utils/csrf/react";
import { AlertTriangle, CheckCircle2, Download, KeyRound, RefreshCw, ShieldCheck, UserCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import SettingsSubtabs from "../components/settings/SettingsSubtabs";
import { httpApp } from "../utils/http.client";
import type { ApplianceUpdateAction, ApplianceUpdateStatus } from "../utils/applianceUpdateStatus";
import { summarizeApplianceUpdateStatus } from "../utils/applianceUpdateStatus";
import { getAuthFromRequest } from "../utils/auth/auth.server";
import { changeLocalAdminPassword } from "../utils/auth/password-change.server";
import { CSRF_FORM_DATA_KEY } from "../utils/csrf/constants";
import { withCsrfValidation } from "../utils/csrf/csrfWrapper.server";

type LoaderData = {
  username: string;
  role: "Super User";
  deployment: "local";
  requiresPasswordChange: boolean;
};

type ActionData = {
  success?: string;
  error?: string;
};

export function meta() {
  return [{ title: "Account - Settings - Unicron" }, { name: "description", content: "Manage the local administrator account" }];
}

export async function loader({ request }: LoaderFunctionArgs) {
  const auth = await getAuthFromRequest(request);
  const user = auth.user ?? {};
  const username = String(user.username ?? user.displayUsername ?? user.name ?? auth.adminBootstrap?.username ?? "admin");

  return data<LoaderData>({
    username,
    role: "Super User",
    deployment: "local",
    requiresPasswordChange: Boolean(auth.adminBootstrap?.requiresPasswordChange),
  });
}

export const action = withCsrfValidation(async ({ request }: ActionFunctionArgs) => {
  const form = await request.formData();

  if (form.get("_intent") !== "change-password") {
    return data<ActionData>({ error: "Unsupported account action." }, { status: 400 });
  }

  const result = await changeLocalAdminPassword(request, {
    currentPassword: String(form.get("currentPassword") ?? ""),
    newPassword: String(form.get("newPassword") ?? ""),
    revokeOtherSessions: true,
    clearBootstrapNoticeDismissal: true,
  });

  if (!result.ok) {
    return data<ActionData>({ error: result.message }, { status: result.status });
  }

  return data<ActionData>({ success: "Password updated." }, { headers: result.headers });
});

function IdentityRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-md border-b border-neutral/10 py-xs last:border-b-0">
      <span className="text-sm text-neutral">{label}</span>
      <span className="min-w-0 truncate text-sm font-medium text-text">{value}</span>
    </div>
  );
}

function LocalAdminNote() {
  return (
    <div className="mt-sm border-t border-neutral/10 pt-sm">
      <div className="flex items-start gap-xs">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-primary" aria-hidden="true" />
        <div className="min-w-0 text-xs text-neutral">
          <p className="font-semibold uppercase">Access model</p>
          <p className="mt-1">LogForge Unicron uses local single-administrator access for this appliance.</p>
        </div>
      </div>
    </div>
  );
}

function ApplianceUpdatesSection() {
  const [status, setStatus] = useState<ApplianceUpdateStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [action, setAction] = useState<ApplianceUpdateAction>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const refreshStatus = async () => {
    const response = await httpApp.get<ApplianceUpdateStatus>("/appliance/update/status");
    setStatus(response.data);
  };

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    httpApp
      .get<ApplianceUpdateStatus>("/appliance/update/status")
      .then((response) => {
        if (!cancelled) setStatus(response.data);
      })
      .catch((error) => {
        if (!cancelled) {
          setStatus({
            status: "degraded",
            updater_health: "unavailable",
            auto_update_enabled: true,
            in_progress: false,
            update_available: false,
            rollback_available: false,
            check_state: "check_failed",
            last_error: error instanceof Error ? error.message : "Appliance updater is unavailable.",
          });
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const runUpdateAction = async (name: Exclude<ApplianceUpdateAction, null>, path: string) => {
    setAction(name);
    setActionError(null);
    try {
      const response = await httpApp.post<ApplianceUpdateStatus>(path, {});
      setStatus(response.data);
    } catch (error) {
      setActionError(error instanceof Error ? error.message : "Update request failed.");
      await refreshStatus().catch(() => undefined);
    } finally {
      setAction(null);
    }
  };

  const busy = Boolean(action) || Boolean(status?.in_progress);
  const summary = useMemo(() => {
    return summarizeApplianceUpdateStatus({ status, loading, action, actionError });
  }, [action, actionError, loading, status]);
  const pending = loading || Boolean(action) || Boolean(status?.in_progress);
  const warning = summary.tone === "warning";
  const StatusIcon = pending ? RefreshCw : warning ? AlertTriangle : status?.update_available ? Download : CheckCircle2;
  const iconClassName = pending ? "text-primary" : warning ? "text-warning-text" : summary.tone === "success" ? "text-success" : "text-primary";

  return (
    <section className="rounded-lg border border-neutral/20 bg-background p-md">
      <div className="flex flex-col gap-sm sm:flex-row sm:items-center sm:justify-between">
        <div className="flex min-w-0 items-start gap-sm">
          <StatusIcon className={`mt-0.5 h-5 w-5 shrink-0 ${iconClassName}`} />
          <div className="min-w-0">
            <h2 className="text-sm font-semibold text-text">Unicron Updates</h2>
            <p className={`mt-1 text-sm ${warning ? "text-warning-text" : "text-neutral"}`} role={warning ? "status" : undefined}>
              {summary.message}
            </p>
          </div>
        </div>
        <div className="flex w-full flex-col gap-xs sm:w-auto sm:flex-row">
          <button
            type="button"
            className="inline-flex items-center justify-center gap-2 rounded-md border border-neutral/20 px-sm py-xs text-sm font-semibold text-text transition-colors hover:bg-neutral/5 disabled:cursor-not-allowed disabled:opacity-60"
            disabled={loading || busy}
            onClick={() => runUpdateAction("check", "/appliance/update/check")}
          >
            <RefreshCw className="h-4 w-4" />
            Check Now
          </button>
          {status?.update_available ? (
            <button
              type="button"
              className="inline-flex items-center justify-center gap-2 rounded-md bg-primary px-sm py-xs text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={loading || busy || status.updater_health !== "ok"}
              onClick={() => runUpdateAction("apply", "/appliance/update/apply")}
            >
              <Download className="h-4 w-4" />
              Pull & Restart
            </button>
          ) : null}
        </div>
      </div>
    </section>
  );
}

export default function AccountSettingsPage() {
  const { username, role, deployment, requiresPasswordChange } = useLoaderData<typeof loader>();
  const actionData = useActionData<typeof action>();
  const navigation = useNavigation();
  const isSubmitting = navigation.state === "submitting";

  return (
    <div className="flex w-full flex-col gap-lg">
      <div className="flex flex-col gap-sm">
        <div className="flex items-center gap-xs">
          <UserCircle className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold text-text">Account</h1>
        </div>
        <p className="text-sm text-neutral">Manage the signed-in local administrator.</p>
      </div>

      <SettingsSubtabs />

      <div className="grid gap-md lg:grid-cols-[minmax(260px,360px)_minmax(0,1fr)]">
        <section className="rounded-xl border border-neutral/20 bg-background p-md">
          <div className="flex items-center gap-xs">
            <UserCircle className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold text-text">Signed-in Identity</h2>
          </div>
          <div className="mt-sm">
            <IdentityRow label="Username" value={username} />
            <IdentityRow label="Role" value={role} />
            <IdentityRow label="Deployment" value={deployment} />
          </div>
          <LocalAdminNote />
          {requiresPasswordChange ? (
            <p className="mt-sm rounded-md border border-warning/40 bg-warning/10 p-xs text-xs text-warning-text">This administrator password should be changed.</p>
          ) : null}
        </section>

        <section className="rounded-xl border border-neutral/20 bg-background p-md">
          <div className="flex items-center gap-xs">
            <KeyRound className="h-5 w-5 text-primary" />
            <h2 className="text-sm font-semibold text-text">Change Password</h2>
          </div>
          <Form method="post" className="mt-sm grid gap-sm">
            <AuthenticityTokenInput name={CSRF_FORM_DATA_KEY} />
            <input type="hidden" name="_intent" value="change-password" />
            {actionData?.error ? (
              <p className="rounded-md border border-error/70 bg-error/10 p-xs text-sm text-error" role="alert">
                {actionData.error}
              </p>
            ) : null}
            {actionData?.success ? (
              <p className="rounded-md border border-success/70 bg-success/10 p-xs text-sm text-success" role="status">
                {actionData.success}
              </p>
            ) : null}
            <label className="grid gap-1 text-sm font-medium text-text">
              Current password
              <input
                type="password"
                name="currentPassword"
                autoComplete="current-password"
                className="rounded-md border border-neutral/20 bg-background px-sm py-xs text-sm font-normal text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                required
                disabled={isSubmitting}
              />
            </label>
            <label className="grid gap-1 text-sm font-medium text-text">
              New password
              <input
                type="password"
                name="newPassword"
                autoComplete="new-password"
                className="rounded-md border border-neutral/20 bg-background px-sm py-xs text-sm font-normal text-text outline-none focus:border-primary focus:ring-2 focus:ring-primary/20"
                required
                disabled={isSubmitting}
              />
            </label>
            <p className="text-xs text-neutral">Use 8-128 characters with uppercase, lowercase, number, and special character.</p>
            <button
              type="submit"
              className="w-fit rounded-md bg-primary px-sm py-xs text-sm font-semibold text-white transition-colors hover:bg-primary/90 disabled:cursor-not-allowed disabled:opacity-60"
              disabled={isSubmitting}
            >
              {isSubmitting ? "Saving..." : "Save password"}
            </button>
          </Form>
        </section>
      </div>

      <ApplianceUpdatesSection />
    </div>
  );
}
