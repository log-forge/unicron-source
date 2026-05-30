import type { AgentStatus } from "./agentFailure";

export type RemovableAgent = {
  agent_id: string;
  agent_name: string;
};

export function getAgentRemovalLabel(status: AgentStatus): "Remove" | "Decommission" {
  return status === "blocked" ? "Remove" : "Decommission";
}

export function getAgentRemovalPendingLabel(status: AgentStatus): "Removing..." | "Decommissioning..." {
  return status === "blocked" ? "Removing..." : "Decommissioning...";
}

export function buildAgentRemovalConfirmation(agentName: string, status: AgentStatus): string {
  if (status === "blocked") {
    return `Remove refused agent "${agentName}"?\n\nThis hides the refused agent and invalidates its enrollment identity. Enroll the host again to try again.`;
  }

  return `Are you sure you want to decommission agent "${agentName}"?\n\nThis will disconnect the agent immediately and remove it from the list.`;
}

export function buildAgentDeregisterPath(agentId: string): string {
  return `/agent/${encodeURIComponent(agentId)}/deregister`;
}

export function removeAgentFromRows<T extends RemovableAgent>(
  agents: T[] | undefined,
  agentId: string,
  agentName?: string,
): T[] {
  const name = agentName || agentId;
  return (agents || []).filter((agent) => agent.agent_id !== agentId && agent.agent_name !== name);
}
