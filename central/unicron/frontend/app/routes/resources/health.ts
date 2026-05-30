import { log } from "../../utils/logging/logger.server";
import type { Route } from "./+types/health";
import { data } from "react-router";

export async function loader({}: Route.LoaderArgs) {
  // Minimal fast path for container healthcheck
  return data({ success: true, status: "healthy" }, { status: 200, headers: { "Content-Type": "application/json" } });
}

// Optional action (POST) retained for parity; returns same shape
export async function action({}: Route.ActionArgs) {
  log.info("Health action invoked");
  return data({ success: true, status: "healthy" }, { status: 200, headers: { "Content-Type": "application/json" } });
}
