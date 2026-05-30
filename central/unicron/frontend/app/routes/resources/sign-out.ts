import { redirect, type ActionFunctionArgs } from "react-router";

import { LEGACY_AUTH_COOKIE_NAME } from "../../utils/auth/constants";
import { withCsrfValidation } from "../../utils/csrf/csrfWrapper.server";
import { createServerHttpClient } from "../../utils/http.server";

function appendSetCookieHeaders(headers: Headers, setCookie: string | string[] | undefined) {
  for (const cookie of Array.isArray(setCookie) ? setCookie : setCookie ? [setCookie] : []) {
    headers.append("Set-Cookie", cookie);
  }
}

function expireLegacyBearerCookies(headers: Headers) {
  const expired = `${LEGACY_AUTH_COOKIE_NAME}=; Expires=Thu, 01 Jan 1970 00:00:00 GMT; Max-Age=0; SameSite=Lax`;
  headers.append("Set-Cookie", `${expired}; Path=/`);
  headers.append("Set-Cookie", `${expired}; Path=/unicron`);
}

export const action = withCsrfValidation(async ({ request }: ActionFunctionArgs) => {
  const headers = new Headers();
  const client = createServerHttpClient({ base: "auth", request });
  const response = await client.post("/api/auth/sign-out", null, { validateStatus: () => true }).catch(() => null);

  appendSetCookieHeaders(headers, response?.headers["set-cookie"]);
  expireLegacyBearerCookies(headers);

  return redirect("/sign-in", { headers });
});
