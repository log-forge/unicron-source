import type { ActionFunction, LoaderFunction } from "react-router";
import { csrf } from "./csrf.server";

/**
 * Wrap a loader or action with CSRF validation.
 *
 * - Only mutating methods are checked (POST, PUT, DELETE, PATCH).
 * - Supports both `application/json` and form-based bodies.
 * - Returns a 403 JSON response if validation fails.
 */
export function withCsrfValidation<T extends LoaderFunction | ActionFunction>(fn: T): T {
  return (async (args) => {
    const { request } = args;
    const mutatingMethods = ["POST", "PUT", "DELETE", "PATCH"];

    if (mutatingMethods.includes(request.method.toUpperCase())) {
      try {
        // Clone the request so we do not consume the original body.
        const clonedRequest = request.clone();
        const params = new URLSearchParams();
        const contentType = request.headers.get("Content-Type") ?? "";

        if (contentType.includes("application/json")) {
          // JSON: convert into URLSearchParams so remix-utils can read it.
          const jsonData = await clonedRequest.json();
          Object.entries(jsonData as Record<string, unknown>).forEach(([key, value]) => {
            if (value !== undefined && value !== null) {
              params.append(key, String(value));
            }
          });
        } else {
          // Default: treat as form-data (standard form posts / fetcher submits).
          const formData = await clonedRequest.formData();
          for (const [key, value] of formData.entries()) {
            params.append(key, value.toString());
          }
        }

        // Build a new request for CSRF validation.
        const csrfRequest = new Request(request.url, {
          method: request.method,
          headers: {
            ...Object.fromEntries(request.headers.entries()),
            "Content-Type": "application/x-www-form-urlencoded",
          },
          body: params,
        });

        // Validate using remix-utils CSRF helper.
        await csrf.validate(csrfRequest);
      } catch (error: any) {
        console.error("CSRF validation error:", error);
        return new Response(JSON.stringify({ error: { message: error?.message || "CSRF validation failed" } }), {
          status: 403,
          headers: { "Content-Type": "application/json" },
        });
      }
    }

    // If we reach here, validation passed or the method is non-mutating.
    return await fn(args);
  }) as T;
}
