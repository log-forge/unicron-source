export type AgentStatus = "online" | "offline" | "blocked";

export type AgentFailure = {
  code: string;
  message?: string | null;
};

export type AgentFailureDisplay = {
  statusLabel: "Online" | "Offline" | "Refused";
  message?: string;
  detail?: string;
  compactDetail?: string;
};

export function getAgentStatusLabel(status: AgentStatus): AgentFailureDisplay["statusLabel"] {
  if (status === "online") return "Online";
  if (status === "blocked") return "Refused";
  return "Offline";
}

export function buildAgentFailureDisplay(status: AgentStatus, failure?: AgentFailure | null): AgentFailureDisplay {
  const statusLabel = getAgentStatusLabel(status);
  if (status !== "blocked") return { statusLabel };

  return {
    statusLabel,
    message: failure?.message || "This agent is not connected because registration was refused.",
    compactDetail: failure?.code || "Registration refused",
  };
}
