import { createAuthClient } from "better-auth/react";
import { clientEnv } from "../env.client";
import { LEGACY_AUTH_COOKIE_NAME, LEGACY_AUTH_STORAGE_KEY } from "./constants";

function resolveAuthBaseUrl(): string {
  const configured = clientEnv?.VITE_AUTH_BASE_URL ?? clientEnv?.VITE_APP_BASE_URL ?? "";
  if (/^https?:\/\//iu.test(configured)) return configured.replace(/\/+$/u, "");

  const origin = typeof window !== "undefined" ? window.location.origin : "http://localhost";
  const path = configured || "/";
  return new URL(path, origin).toString().replace(/\/+$/u, "");
}

const baseURL = resolveAuthBaseUrl();

type AuthResponse<T = unknown> = {
  data?: T | null;
  error?: { message?: string; code?: string; status?: number } | null;
};

export function clearLegacyAuthStorage(): void {
  if (typeof window === "undefined") return;
  localStorage.removeItem(LEGACY_AUTH_STORAGE_KEY);
  const expired = "expires=Thu, 01 Jan 1970 00:00:00 GMT";
  document.cookie = `${LEGACY_AUTH_COOKIE_NAME}=; path=/; ${expired}`;
  document.cookie = `${LEGACY_AUTH_COOKIE_NAME}=; path=/unicron; ${expired}`;
}

export const authClient = createAuthClient({
  baseURL,
  fetchOptions: {
    credentials: "include",
  },
});

export async function signInWithUsername(input: { username: string; password: string }): Promise<AuthResponse> {
  const response = await fetch(`${baseURL.replace(/\/+$/u, "")}/api/auth/sign-in/username`, {
    method: "POST",
    credentials: "include",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(input),
  });

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    return {
      data: null,
      error: {
        message:
          payload?.message ??
          payload?.error?.message ??
          payload?.code ??
          "Unable to sign in. Please try again.",
        code: payload?.code ?? payload?.error?.code,
        status: response.status,
      },
    };
  }

  return { data: payload ?? {}, error: null };
}

export const { useSession, changePassword } = authClient;

export async function signOut(): Promise<AuthResponse> {
  try {
    const response = await fetch(`${baseURL.replace(/\/+$/u, "")}/api/auth/sign-out`, {
      method: "POST",
      credentials: "include",
    });
    const payload = await response.json().catch(() => null);

    if (!response.ok) {
      return {
        data: null,
        error: {
          message: payload?.message ?? payload?.error?.message ?? payload?.code ?? "Unable to sign out.",
          code: payload?.code ?? payload?.error?.code,
          status: response.status,
        },
      };
    }

    return { data: payload ?? {}, error: null };
  } catch (_err) {
    return { data: null, error: { message: "Unable to sign out." } };
  } finally {
    clearLegacyAuthStorage();
  }
}

export type AuthUser = Record<string, unknown> & {
  id?: string;
  username?: string;
  displayUsername?: string;
  name?: string | null;
  image?: string | null;
  createdAt?: string;
  updatedAt?: string;
};

export type AuthUserSession = Record<string, unknown> & {
  id?: string;
  userId?: string;
  expiresAt?: string;
  createdAt?: string;
  updatedAt?: string;
};

export type AuthActiveOrganization = { id: string; name?: string };
export type AuthOrganization = AuthActiveOrganization;
export type AuthOrganizationInvitation = Record<string, unknown>;
export type AuthOrganizationMember = Record<string, unknown>;
export type AuthOrganizationTeam = Record<string, unknown>;
