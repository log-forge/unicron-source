import { createServerHttpClient } from "../http.server";
import type { AuthActiveOrganization, AuthUser, AuthUserSession, AuthOrganizationTeam } from "./auth-client";

export type BetterAuthSession = {
  user: AuthUser | null;
  session: AuthUserSession | null;
  organization: AuthActiveOrganization | null;
  organizationRole: string | null;
  team: AuthOrganizationTeam | null;
  teamIds: string[];
  adminBootstrap: {
    enabled: boolean;
    username: string;
    requiresPasswordChange: boolean;
  } | null;
};

export type PermissionShape = Record<string, string[]>;

const AUTH_ME_PATH = "/api/v1/profile";

const authCache = new WeakMap<Request, Promise<BetterAuthSession>>();

const anonymousAuth = (): BetterAuthSession => ({
  user: null,
  session: null,
  organization: null,
  organizationRole: null,
  team: null,
  teamIds: [],
  adminBootstrap: null,
});

async function fetchAuthFromRequest(request: Request): Promise<BetterAuthSession> {
  const client = createServerHttpClient({ base: "auth", request, includeCookies: true });

  try {
    // Accept non-200 as "unauthenticated" instead of throwing
    const res = await client.get<{ status?: string; data?: any }>(AUTH_ME_PATH, { validateStatus: () => true });
    if (res.status !== 200) return anonymousAuth();

    const payload = res.data ?? {};
    const inner = payload.data ?? {};
    const user = inner.user ?? null;
    const username = user?.username ?? user?.displayUsername ?? user?.name ?? "";
    return {
      user,
      session: inner.session ?? null,
      organization: { id: inner.deploymentId ?? "local", name: "Local appliance" },
      organizationRole: "admin",
      team: inner.team ?? null,
      teamIds: [],
      adminBootstrap: {
        enabled: true,
        username,
        requiresPasswordChange: Boolean(inner.requiresPasswordChange),
      },
    };
  } catch (_err) {
    // Network or unexpected error – also treat as anonymous
    return anonymousAuth();
  }
}

export async function getAuthFromRequest(request: Request): Promise<BetterAuthSession> {
  let authPromise = authCache.get(request);
  if (!authPromise) {
    authPromise = fetchAuthFromRequest(request);
    authCache.set(request, authPromise);
  }

  return authPromise;
}
