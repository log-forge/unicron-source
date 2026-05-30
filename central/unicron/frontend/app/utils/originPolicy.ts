export interface OriginPolicy {
  effective_allowed_origins: string[];
  stored_allowed_origins: string[];
  protected_allowed_origins: string[];
  origin_policy_source: "env" | "db" | "default" | string;
  origin_policy_managed_by_env: boolean;
  origin_policy_ui_editable: boolean;
  origin_policy_same_origin_only: boolean;
}

export interface OriginPolicyDisplay {
  requiredOrigins: string[];
  additionalOrigins: string[];
  allowedOrigins: string[];
}

export function mergeOriginLists(
  ...originLists: Array<Iterable<string | null | undefined> | null | undefined>
): string[] {
  const merged: string[] = [];
  const seen = new Set<string>();

  for (const originList of originLists) {
    if (!originList) continue;
    for (const value of originList) {
      const origin = (value || "").trim();
      if (!origin || seen.has(origin)) continue;
      seen.add(origin);
      merged.push(origin);
    }
  }

  return merged;
}

export function parseOriginDraft(draft: string): string[] {
  return mergeOriginLists(draft.split(/[\n,]/g));
}

export function filterEditableOrigins(origins: Iterable<string>, requiredOrigins: Iterable<string>): string[] {
  const required = new Set(mergeOriginLists(requiredOrigins));
  return mergeOriginLists(origins).filter((origin) => !required.has(origin));
}

export function formatOriginDraft(origins: Iterable<string>): string {
  return mergeOriginLists(origins).join("\n");
}

export function buildOriginPolicyDisplay(
  policy: OriginPolicy | undefined,
  currentUiOrigin: string | null | undefined,
): OriginPolicyDisplay {
  const requiredOrigins = mergeOriginLists(
    policy?.protected_allowed_origins,
    currentUiOrigin ? [currentUiOrigin] : undefined,
  );
  const additionalOrigins = filterEditableOrigins(policy?.stored_allowed_origins || [], requiredOrigins);
  const allowedOrigins = mergeOriginLists(requiredOrigins, policy?.effective_allowed_origins, additionalOrigins);

  return {
    requiredOrigins,
    additionalOrigins,
    allowedOrigins,
  };
}
