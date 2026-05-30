import { PasswordSchema } from "../../schemas/auth.schemas";
import { clearBootstrapPasswordNoticeDismissal } from "../cookies/bootstrap-password-notice.server";
import { createServerHttpClient } from "../http.server";

export type PasswordChangeFailureKind = "invalid" | "failed";

export type PasswordChangeResult =
  | {
      ok: true;
      headers: Headers;
    }
  | {
      ok: false;
      kind: PasswordChangeFailureKind;
      message: string;
      status: number;
    };

function passwordPolicyMessage(rawPassword: string): string | null {
  const parsed = PasswordSchema.safeParse(rawPassword);
  if (parsed.success) return null;
  return parsed.error.issues.map((issue) => issue.message).join("; ");
}

function appendSetCookieHeaders(headers: Headers, setCookie: string | string[] | undefined) {
  for (const cookie of Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : []) {
    headers.append("Set-Cookie", cookie);
  }
}

function responseMessage(payload: unknown): string | null {
  const body = payload as any;
  return body?.message ?? body?.error?.message ?? body?.code ?? null;
}

function authPasswordChangeError(status: number, payload: unknown): string {
  if (status === 401) return "Session expired. Sign in again and retry.";
  if (status === 400 || status === 403) return "Current password is incorrect.";
  return responseMessage(payload) ?? "Could not change the password. Try again.";
}

export async function changeLocalAdminPassword(
  request: Request,
  input: {
    currentPassword: string;
    newPassword: string;
    revokeOtherSessions?: boolean;
    clearBootstrapNoticeDismissal?: boolean;
  },
): Promise<PasswordChangeResult> {
  const currentPassword = input.currentPassword;
  const newPassword = input.newPassword;

  if (!currentPassword) {
    return { ok: false, kind: "invalid", message: "Enter your current password.", status: 400 };
  }

  const policyMessage = passwordPolicyMessage(newPassword);
  if (policyMessage) {
    return { ok: false, kind: "invalid", message: policyMessage, status: 400 };
  }

  const client = createServerHttpClient({ base: "auth", request });
  const response = await client
    .post(
      "/api/auth/change-password",
      {
        currentPassword,
        newPassword,
        revokeOtherSessions: input.revokeOtherSessions ?? true,
      },
      { validateStatus: () => true },
    )
    .catch(() => null);

  if (!response || response.status < 200 || response.status >= 300) {
    return {
      ok: false,
      kind: "failed",
      message: response ? authPasswordChangeError(response.status, response.data) : "Could not reach Central Auth. Try again.",
      status: response?.status ?? 502,
    };
  }

  const headers = new Headers();
  appendSetCookieHeaders(headers, response.headers["set-cookie"]);

  if (input.clearBootstrapNoticeDismissal) {
    headers.append("Set-Cookie", await clearBootstrapPasswordNoticeDismissal());
  }

  return { ok: true, headers };
}
