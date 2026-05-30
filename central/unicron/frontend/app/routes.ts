import { type RouteConfig, index, layout, prefix, route } from "@react-router/dev/routes";

export default [
  ...prefix("resources", [
    route("health", "routes/resources/health.ts"),
    route("theme-switch", "routes/resources/theme-switch.ts"),
    route("sign-out", "routes/resources/sign-out.ts"),
  ]),
  layout("routes/layouts/auth-provider.tsx", { id: "auth-provider" }, [
    route("sign-in", "routes/sign-in.tsx"),
    layout("routes/layouts/auth-required.tsx", [
      layout("routes/layouts/deployment-org-required.tsx", [
        layout("routes/layouts/app-shell.tsx", [
          layout("routes/layouts/base-layout.tsx", [
            // Canonical main page path
            index("routes/overview.tsx"),
            route("overview", "routes/containers.tsx"),
            // Typo-safe redirect alias -> canonical /overview
            route("continers", "routes/continers.tsx"),
            // Alerting section - layout handles all internal tab routing via client-side state
            ...prefix("alerting", [
              index("routes/alerting/_layout.tsx"),
              route("*", "routes/alerting/_layout.tsx", { id: "alerting-catchall" }),
            ]),
            // Notifications section - layout handles all internal tab routing via client-side state
            ...prefix("notifications", [
              index("routes/notifications/_layout.tsx"),
              route("*", "routes/notifications/_layout.tsx", { id: "notifications-catchall" }),
            ]),
            // Legacy /containers route redirects to /overview
            route("containers", "routes/overview.tsx", { id: "containers-explicit" }),
            route("containers/host/:hostId", "routes/containers/host.$hostId.tsx"),
            route("containers/:id", "routes/containers/$id.tsx"),
            // Settings section
            ...prefix("settings", [
              index("routes/settings.index.tsx"),
              route("account", "routes/settings.account.tsx"),
              route("agents", "routes/settings.agents.tsx"),
              route("origins", "routes/settings.origins.tsx"),
              route("storage", "routes/settings.storage.tsx"),
            ]),
            ...prefix("showcase", [
              route("buttons", "routes/showcases/button-showcase.tsx"),
              route("inputs", "routes/showcases/input-showcase.tsx"),
              route("checkboxes", "routes/showcases/checkbox-showcase.tsx"),
              route("combo-boxes", "routes/showcases/combo-box-showcase.tsx"),
              route("text-fields", "routes/showcases/text-field-showcase.tsx"),
              route("number-fields", "routes/showcases/number-field-showcase.tsx"),
              route("tabs", "routes/showcases/tabs-showcase.tsx"),
            ]),
          ]),
        ]),
      ]),
    ]),
  ]),
] satisfies RouteConfig;
