import { createCookie } from "react-router";

export const bootstrapPasswordNoticeCookie = createCookie("unicron-bootstrap-password-notice", {
  path: "/",
  httpOnly: true,
  sameSite: "lax",
  secure: process.env.VITE_NODE_ENV === "production",
  maxAge: 60 * 60 * 24 * 30,
});

export async function isBootstrapPasswordNoticeDismissed(request: Request): Promise<boolean> {
  return (await bootstrapPasswordNoticeCookie.parse(request.headers.get("Cookie"))) === "dismissed";
}

export function dismissBootstrapPasswordNotice(): Promise<string> {
  return bootstrapPasswordNoticeCookie.serialize("dismissed");
}

export function clearBootstrapPasswordNoticeDismissal(): Promise<string> {
  return bootstrapPasswordNoticeCookie.serialize("", { maxAge: 0 });
}
