import "react-router";
import type { AppLogger } from "../utils/logging/logger.server";
import type { AuthActiveOrganization, AuthOrganization, AuthUserSession, AuthUser } from "../utils/auth/auth-client";

declare global {
  interface Request {
    user?: AuthUser | null;
    session?: AuthUserSession | null;
    organization?: AuthActiveOrganization | AuthOrganization | null;
    deploymentOrgId?: string | null;
    hasPermissions?: boolean;
  }

  type FontSize = "h1" | "h2" | "h3" | "h4" | "h5" | "base" | "sm" | "xs" | "2xs";
  type Spacing = "0" | "4xs" | "3xs" | "2xs" | "xs" | "sm" | "md" | "lg" | "xl" | "2xl" | "3xl" | "4xl";
  type Radius = "none" | "sm" | "md" | "lg" | "full";
  type SpeacialColor =
    | "background"
    | "foreground"
    | "alt-background"
    | "alt-foreground"
    | "divider"
    | "text"
    | "success-text"
    | "warning-text"
    | "error-text"
    | "neutral-text"
    | "alt-text"
    | "highlight-text"
    | "shadow";
  type ColorName = "primary" | "secondary" | "success" | "warning" | "error" | "neutral";
  type ColorShade = "50" | "100" | "200" | "300" | "400" | "500" | "600" | "700" | "800" | "900" | "950";
  type Colors = `${ColorName}-${ColorShade}` | ColorName | `${ColorName}-${ColorShade}/${number}` | `${ColorName}/${number}` | SpeacialColor | `${SpeacialColor}/${number}`;
}

declare module "react-router" {
  interface AppLoadContext {
    log: AppLogger;
  }
}
