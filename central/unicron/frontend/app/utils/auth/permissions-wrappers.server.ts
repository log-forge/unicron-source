import { data, type LoaderFunctionArgs, type ActionFunctionArgs } from "react-router";
import { withAuth, type AuthOptions } from "./auth-wrappers.server";
import type { PermissionShape } from "./auth.server";

type LoaderOrActionArgs = LoaderFunctionArgs | ActionFunctionArgs;

export function withPermissions<T>(_permissions: PermissionShape, handler: (args: LoaderOrActionArgs) => Promise<T>, options: AuthOptions = {}) {
  return withAuth(async (args) => {
    const { request } = args;

    request.hasPermissions = Boolean(request.user && request.session);
    return handler(args);
  }, options);
}

export function requirePermissions<T>(permissions: PermissionShape, handler: (args: LoaderOrActionArgs) => Promise<T>, options: AuthOptions = {}) {
  return withPermissions(
    permissions,
    async (args) => {
      const { request } = args;

      if (!request.user || !request.session) {
        throw data({ success: false, error: "Unauthorized" }, { status: 401, headers: { "Content-Type": "application/json" } });
      }

      if (!request.hasPermissions) {
        throw data({ success: false, error: "Admin session required" }, { status: 403, headers: { "Content-Type": "application/json" } });
      }

      return handler(args);
    },
    options,
  );
}

export function withOrganization<T>(handler: (args: LoaderOrActionArgs) => Promise<T>, options: AuthOptions = {}) {
  return withAuth(handler, options);
}

export function requireOrganization<T>(handler: (args: LoaderOrActionArgs) => Promise<T>, options: AuthOptions = {}) {
  return withOrganization(async (args) => {
    const { request } = args;

    if (!request.user || !request.session) {
      throw data({ success: false, error: "Unauthorized" }, { status: 401, headers: { "Content-Type": "application/json" } });
    }

    return handler(args);
  }, options);
}
