import { createCookie } from "react-router";
import { CSRF } from "remix-utils/csrf/server";
import { CSRF_COOKIE_NAME, CSRF_FORM_DATA_KEY } from "./constants";

if (!process.env.CSRF_COOKIE_SECRET || !process.env.CSRF_SECRET) {
  throw new Error("CSRF_COOKIE_SECRET and CSRF_SECRET must be set");
}

export const csrfCookie = createCookie(CSRF_COOKIE_NAME, {
  path: "/unicron",
  httpOnly: true,
  secure: process.env.NODE_ENV === "production",
  sameSite: "lax",
  secrets: [process.env.CSRF_COOKIE_SECRET!],
});

export const csrf = new CSRF({
  cookie: csrfCookie,
  // key used in FormData / body
  formDataKey: CSRF_FORM_DATA_KEY,
  // optional secret used to sign the token, recommended
  secret: process.env.CSRF_SECRET,
});
