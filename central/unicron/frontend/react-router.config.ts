import type { Config } from "@react-router/dev/config";

export default {
  // Config options...
  // Server-side render by default, to enable SPA mode set this to `false`
  ssr: true,
  // Ensure the server build renders asset links with the /unicron prefix so
  // Traefik (which strips /unicron before proxying) receives the correct
  // paths. This sets the public path used when generating server HTML.
  basename: "/unicron",
} satisfies Config;
