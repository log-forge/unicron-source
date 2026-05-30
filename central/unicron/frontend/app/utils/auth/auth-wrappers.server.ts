import { data, type LoaderFunctionArgs, type ActionFunctionArgs } from "react-router";
import { getAuthFromRequest } from "./auth.server";

type LoaderOrActionArgs = LoaderFunctionArgs | ActionFunctionArgs;

export type AuthOptions = Record<string, never>;

export function withAuth<T>(handler: (args: LoaderOrActionArgs) => Promise<T>, options: AuthOptions = {}) {
  return async (args: LoaderOrActionArgs) => {
    const { request } = args;
    const auth = await getAuthFromRequest(request);

    request.user = auth.user ?? null;
    request.session = auth.session ?? null;
    request.organization = auth.organization ?? null;
    return handler(args);
  };
}

export function requireAuth<T>(handler: (args: LoaderOrActionArgs) => Promise<T>, options: AuthOptions = {}) {
  return withAuth(async (args) => {
    const { request } = args;
    if (!request.user || !request.session) {
      throw data({ success: false, error: "Unauthorized" }, { status: 401, headers: { "Content-Type": "application/json" } });
    }

    return handler(args);
  }, options);
}
