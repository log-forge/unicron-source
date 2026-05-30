import type { Route } from "../../../.react-router/types/app/routes/resources/+types/theme-switch";
import { setTheme } from "../../utils/cookies/theme.server";

export async function action({ request }: Route.ActionArgs) {
  const { theme } = await request.json();

  console.log("new theme", theme);

  const cookieHeader = await setTheme(theme);

  return new Response(JSON.stringify({ success: true }), {
    headers: {
      "Content-Type": "application/json",
      "Set-Cookie": cookieHeader,
    },
  });
}
