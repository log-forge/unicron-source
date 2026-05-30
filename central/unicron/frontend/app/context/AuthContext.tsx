import React, { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  useSession,
  clearLegacyAuthStorage,
  type AuthUserSession,
  type AuthUser,
  type AuthActiveOrganization,
  type AuthOrganization,
  type AuthOrganizationTeam,
} from "../utils/auth/auth-client";
import type { BetterAuthSession } from "../utils/auth/auth.server";
import { clientLog } from "../utils/logging/logger.client";
import { httpAuth } from "../utils/http.client";

type AuthContextValue = {
  /** The authenticated user object returned by Better Auth; null when no user is signed in. */
  user: AuthUser | null;
  /** The active user session (tokens / metadata); null when no session exists. */
  session: AuthUserSession | null;
  /** The organization context; ActiveOrganization from server or basic Organization from client. */
  organization: AuthActiveOrganization | AuthOrganization | null;
  /** The user's role within the active organization; null when no org context exists. */
  organizationRole: string | null;
  /** The active team info; null in the single-admin appliance. */
  team: AuthOrganizationTeam | null;
  /** All team ids the user belongs to within the active organization. */
  teamIds: string[];
  /** Central admin bootstrap state; present only for the configured single-admin account. */
  adminBootstrap: BetterAuthSession["adminBootstrap"];
  /** Convenience flag = true when both `user` and `session` are present. */
  isAuthenticated: boolean;
  /** True while the session hook is resolving (post-hydration). */
  isAuthLoading: boolean;
  /** True while organization list is being fetched client-side. */
  isOrganizationLoading: boolean;
  /** Aggregate loading across auth + organization profile data. */
  isLoading: boolean;
  /** Imperative trigger to re-run the underlying `useSession` hook (e.g. after profile or auth changes). */
  refetch: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children, initial }: { children: React.ReactNode; initial: BetterAuthSession }) {
  const [hydrated, setHydrated] = useState(false);
  const { data, isPending, refetch } = useSession();
  const [organization, setOrganization] = useState<AuthActiveOrganization | AuthOrganization | null>(initial.organization);
  const [organizationRole, setOrganizationRole] = useState<string | null>(initial.organizationRole);
  const [team, setTeam] = useState<AuthOrganizationTeam | null>(initial.team ?? null);
  const [teamIds, setTeamIds] = useState<string[]>(initial.teamIds ?? []);
  const [adminBootstrap, setAdminBootstrap] = useState<BetterAuthSession["adminBootstrap"]>(initial.adminBootstrap);
  const [profileLoading, setProfileLoading] = useState(false);

  useEffect(() => {
    setHydrated(true);
    clientLog.info({ initial }, "AuthProvider hydrated with initial data");
  }, []);

  useEffect(() => {
    setOrganization(initial.organization);
    setOrganizationRole(initial.organizationRole);
    setTeam(initial.team ?? null);
    setTeamIds(initial.teamIds ?? []);
    setAdminBootstrap(initial.adminBootstrap);
  }, [initial.organization, initial.organizationRole, initial.team, initial.teamIds, initial.adminBootstrap]);

  const user: AuthUser | null = (data?.user as AuthUser | undefined) ?? initial.user;
  const session: AuthUserSession | null = (data?.session as AuthUserSession | undefined) ?? initial.session;
  useEffect(() => {
    if (!hydrated || typeof window === "undefined") return;
    clearLegacyAuthStorage();
  }, [hydrated]);

  useEffect(() => {
    if (!hydrated || !user) return;
    const controller = new AbortController();

    const fetchProfile = async () => {
      try {
        setProfileLoading(true);
        const res = await httpAuth.get<{ status?: string; data?: any }>("/api/v1/profile", { signal: controller.signal });
        if (controller.signal.aborted) return;

        const profileData = res.data?.data;
        if (profileData) {
          const profileUser = profileData.user ?? {};
          const username = profileUser.username ?? profileUser.displayUsername ?? profileUser.name ?? "";
          setOrganization({ id: profileData.deploymentId ?? "local", name: "Local appliance" });
          setOrganizationRole("admin");
          setTeam(null);
          setTeamIds([]);
          setAdminBootstrap({
            enabled: true,
            username,
            requiresPasswordChange: Boolean(profileData.requiresPasswordChange),
          });
        }
      } catch (err: any) {
        if (err.name === "CanceledError" || err.name === "AbortError") return;
        clientLog.error({ err }, "Failed to fetch profile via /api/v1/profile");
      } finally {
        if (!controller.signal.aborted) setProfileLoading(false);
      }
    };

    fetchProfile();

    return () => controller.abort();
  }, [hydrated, user]);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      session,
      organization,
      organizationRole,
      team,
      teamIds,
      adminBootstrap,
      isAuthenticated: Boolean(user && session),
      // During SSR + first client paint, prefer initial data; afterwards use the hook's pending state
      isAuthLoading: !hydrated && !!initial.session ? false : isPending,
      isOrganizationLoading: profileLoading,
      isLoading: !hydrated && !!initial.session ? false : Boolean(isPending || profileLoading),
      refetch,
    }),
    [user, session, organization, organizationRole, team, teamIds, adminBootstrap, hydrated, isPending, profileLoading, refetch, initial.session],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");

  return ctx;
}
