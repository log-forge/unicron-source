import type { AgentStatus } from "./agentFailure";

export const ENROLLMENT_POLL_INTERVAL_MS = 2000;
export const ENROLLMENT_POLL_MAX_SECONDS = 60;

export type PendingEnrollment = {
  agentName: string;
  expiresAt: number;
  issuedAt: number;
};

export type EnrollmentPollingAgent = {
  agent_id?: string;
  agent_name?: string;
  status?: AgentStatus | string | null;
};

function normalizeAgentName(name: string | null | undefined): string {
  return (name || "").trim().toLowerCase();
}

export function getEnrollmentPollingCutoffMs(pending: PendingEnrollment): number {
  const maxAgeCutoffMs = (pending.issuedAt + ENROLLMENT_POLL_MAX_SECONDS) * 1000;
  const expiryCutoffMs = pending.expiresAt * 1000;
  return Math.min(maxAgeCutoffMs, expiryCutoffMs);
}

export function findPendingEnrollmentAgent(
  agents: EnrollmentPollingAgent[],
  pending: Pick<PendingEnrollment, "agentName">,
): EnrollmentPollingAgent | undefined {
  const pendingName = normalizeAgentName(pending.agentName);
  return agents.find(
    (agent) =>
      normalizeAgentName(agent.agent_name) === pendingName ||
      normalizeAgentName(agent.agent_id) === pendingName,
  );
}

export function isTerminalEnrollmentStatus(status: EnrollmentPollingAgent["status"]): boolean {
  return status === "blocked" || status === "online" || status === "offline";
}

export function shouldStopEnrollmentPolling(
  pending: PendingEnrollment,
  agents: EnrollmentPollingAgent[],
  nowMs: number,
  isDialogOpen: boolean,
): boolean {
  if (!isDialogOpen) return true;
  if (nowMs >= getEnrollmentPollingCutoffMs(pending)) return true;

  const pendingAgent = findPendingEnrollmentAgent(agents, pending);
  return Boolean(pendingAgent && isTerminalEnrollmentStatus(pendingAgent.status));
}
