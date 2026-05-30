import { useCallback, useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { httpApp } from "../utils/http.client";
import SettingsSubtabs from "../components/settings/SettingsSubtabs";
import {
  buildOriginPolicyDisplay,
  filterEditableOrigins,
  formatOriginDraft,
  parseOriginDraft,
  type OriginPolicy,
  type OriginPolicyDisplay,
} from "../utils/originPolicy";

export function meta() {
  return [
    { title: "Origins - Settings - Unicron" },
    { name: "description", content: "Manage web origin access policy" },
  ];
}

async function fetchOriginPolicy(): Promise<OriginPolicy> {
  const response = await httpApp.get("/settings/origin-policy");
  return response.data as OriginPolicy;
}

async function updateOriginPolicy(allowedOrigins: string[]): Promise<OriginPolicy> {
  const response = await httpApp.put("/settings/origin-policy", {
    allowed_origins: allowedOrigins,
  });
  return response.data as OriginPolicy;
}

interface OriginPolicyCardProps {
  policy: OriginPolicy | undefined;
  loading: boolean;
  saving: boolean;
  draft: string;
  display: OriginPolicyDisplay;
  onDraftChange: (value: string) => void;
  onSave: () => void;
  saveError: string | null;
  saveSuccess: string | null;
}

function OriginPolicyCard({
  policy,
  loading,
  saving,
  draft,
  display,
  onDraftChange,
  onSave,
  saveError,
  saveSuccess,
}: OriginPolicyCardProps) {
  const source = policy?.origin_policy_source ?? "default";
  const envManaged = Boolean(policy?.origin_policy_managed_by_env);
  const uiEditable = policy?.origin_policy_ui_editable ?? !envManaged;
  const sameOriginOnly = Boolean(policy?.origin_policy_same_origin_only);
  const requiredOrigins = display.requiredOrigins;
  const allowedOrigins = display.allowedOrigins;
  const hasRequiredOrigins = requiredOrigins.length > 0;

  return (
    <div className="rounded-xl border border-neutral/20 bg-background p-md">
      <div className="flex flex-col gap-xs">
        <h2 className="text-sm font-semibold text-text">Web Origin Access</h2>
        <p className="text-sm text-neutral">
          Controls which browser origins may call the API and open Socket.IO connections.
        </p>
        <div className="flex flex-wrap gap-xs text-xs text-neutral">
          <span className="rounded-full border border-neutral/20 bg-neutral/5 px-2 py-1 text-text">
            Source: {source}
          </span>
          <span className="rounded-full border border-neutral/20 bg-neutral/5 px-2 py-1 text-text">
            Mode: {sameOriginOnly ? "same-origin only" : "allowlist"}
          </span>
        </div>
      </div>

      {hasRequiredOrigins ? (
        <div className="mt-sm rounded-md border border-neutral/20 bg-neutral/5 p-sm">
          <p className="text-sm font-medium text-text">Required origins</p>
          <p className="mt-1 text-xs text-neutral">
            Current UI and environment origins are always included. These origins cannot be removed here.
          </p>
          <ul className="mt-xs space-y-1 text-xs text-text">
            {requiredOrigins.map((origin) => (
              <li key={origin} className="break-all rounded border border-neutral/20 bg-background px-2 py-1">
                {origin}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <div className="mt-sm space-y-2">
        <label htmlFor="allowed-origins" className="block text-sm font-medium text-text">
          Additional origins
        </label>
        <textarea
          id="allowed-origins"
          value={draft}
          onChange={(event) => onDraftChange(event.target.value)}
          placeholder={`https://app.example.com
https://admin.example.com`}
          rows={5}
          className="w-full rounded-md border border-neutral/20 bg-background px-3 py-2 text-sm text-text placeholder:text-neutral/60 focus:border-primary focus:outline-none focus:ring-2 focus:ring-primary/20 disabled:cursor-not-allowed disabled:opacity-60"
          disabled={loading || saving || !uiEditable}
        />
        <p className="text-xs text-neutral">
          Enter one origin per line or comma-separated. Use exact origins only, including scheme and port when needed.
        </p>
        {hasRequiredOrigins && uiEditable ? (
          <p className="text-xs text-warning">
            Required origins are preserved automatically. Saving here only changes additional origins.
          </p>
        ) : null}
        {!uiEditable ? (
          <p className="text-xs text-warning">
            Managed by environment (`UNICRON_ALLOWED_ORIGINS` or legacy `CORS_ORIGINS`). UI edits are disabled.
          </p>
        ) : null}
        {saveError ? <p className="text-xs text-error">{saveError}</p> : null}
        {saveSuccess ? <p className="text-xs text-success">{saveSuccess}</p> : null}
        <button
          type="button"
          onClick={onSave}
          disabled={loading || saving || !uiEditable}
          className={`
            inline-flex items-center rounded-md px-sm py-xs text-sm font-medium transition-all
            ${
              loading || saving || !uiEditable
                ? "cursor-not-allowed bg-primary/20 text-primary opacity-60"
                : "cursor-pointer bg-primary text-white hover:bg-primary/90"
            }
          `}
        >
          {saving ? "Saving..." : "Save Origin Policy"}
        </button>
      </div>

      <div className="mt-sm rounded-md border border-neutral/20 bg-neutral/5 p-sm">
        <p className="text-sm font-medium text-text">Allowed origins</p>
        <ul className="mt-xs space-y-1 text-xs text-text">
          {allowedOrigins.map((origin) => (
            <li key={origin} className="break-all rounded border border-neutral/20 bg-background px-2 py-1">
              {origin}
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

export default function OriginsPage() {
  const [currentUiOrigin, setCurrentUiOrigin] = useState("");
  const [originDraft, setOriginDraft] = useState("");
  const [originSaving, setOriginSaving] = useState(false);
  const [originSaveError, setOriginSaveError] = useState<string | null>(null);
  const [originSaveSuccess, setOriginSaveSuccess] = useState<string | null>(null);

  const {
    data: originPolicy,
    isLoading: originLoading,
    refetch: refetchOriginPolicy,
  } = useQuery({
    queryKey: ["origin-policy"],
    queryFn: fetchOriginPolicy,
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    setCurrentUiOrigin(window.location.origin);
  }, []);

  const originDisplay = useMemo(
    () => buildOriginPolicyDisplay(originPolicy, currentUiOrigin),
    [originPolicy, currentUiOrigin],
  );

  useEffect(() => {
    if (!originPolicy) return;
    setOriginDraft(formatOriginDraft(originDisplay.additionalOrigins));
  }, [originPolicy, originDisplay.additionalOrigins]);

  const handleSaveOriginPolicy = useCallback(async () => {
    setOriginSaving(true);
    setOriginSaveError(null);
    setOriginSaveSuccess(null);

    const allowedOrigins = filterEditableOrigins(parseOriginDraft(originDraft), originDisplay.requiredOrigins);

    try {
      const updated = await updateOriginPolicy(allowedOrigins);
      const updatedDisplay = buildOriginPolicyDisplay(updated, currentUiOrigin);
      setOriginDraft(formatOriginDraft(updatedDisplay.additionalOrigins));
      setOriginSaveSuccess("Origin policy updated.");
      await refetchOriginPolicy();
    } catch (error: any) {
      setOriginSaveError(error?.response?.data?.detail || "Failed to update origin policy");
    } finally {
      setOriginSaving(false);
    }
  }, [currentUiOrigin, originDisplay.requiredOrigins, originDraft, refetchOriginPolicy]);

  return (
    <div className="flex w-full flex-col gap-lg">
      <div className="flex flex-col gap-sm">
        <div className="flex items-center gap-xs">
          <ShieldCheck className="h-5 w-5 text-primary" />
          <h1 className="text-2xl font-bold text-text">Origins</h1>
        </div>
        <p className="text-sm text-neutral">
          Configure which web origins are allowed to use Central APIs and real-time channels.
        </p>
      </div>

      <SettingsSubtabs />

      <OriginPolicyCard
        policy={originPolicy}
        loading={originLoading}
        saving={originSaving}
        draft={originDraft}
        display={originDisplay}
        onDraftChange={setOriginDraft}
        onSave={handleSaveOriginPolicy}
        saveError={originSaveError}
        saveSuccess={originSaveSuccess}
      />
    </div>
  );
}
