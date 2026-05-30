import { AlertTriangle, Server } from "lucide-react";
import { useNavigate } from "react-router";
import type { ModalInjectedProps } from "../../context/ModalContext";
import { buildAgentFailureDisplay } from "../../utils/agentFailure";
import type { AgentRefusalModalData } from "../../utils/agentRefusalModal";

type AgentRefusalModalProps = ModalInjectedProps & {
  refusal: AgentRefusalModalData;
};

export default function AgentRefusalModal({ refusal, closeModal }: AgentRefusalModalProps) {
  const navigate = useNavigate();
  const display = buildAgentFailureDisplay("blocked", refusal.failure);
  const message = display.message || refusal.failure.message || refusal.reason || "Agent enrollment was refused.";

  const handleViewAgents = () => {
    closeModal?.();
    navigate("/settings/agents");
  };

  return (
    <div className="flex flex-col gap-md">
      <div className="flex items-start gap-sm pr-lg">
        <div className="flex h-lg w-lg shrink-0 items-center justify-center rounded-md bg-warning/10 text-warning-text">
          <AlertTriangle className="h-sm w-sm" aria-hidden="true" />
        </div>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold text-text">Agent not connected</h2>
          <div className="mt-2xs flex min-w-0 items-center gap-2xs text-sm text-neutral">
            <Server className="h-xs w-xs shrink-0" aria-hidden="true" />
            <span className="min-w-0 truncate font-mono text-text">{refusal.herald_name}</span>
          </div>
        </div>
      </div>

      <div className="rounded-md border border-warning/30 bg-warning/10 p-sm">
        <p className="text-sm text-warning-text">{message}</p>
      </div>

      <div className="flex flex-col-reverse gap-xs sm:flex-row sm:justify-end">
        <button
          type="button"
          onClick={handleViewAgents}
          className="inline-flex items-center justify-center gap-2xs rounded-md border border-divider bg-transparent px-sm py-2xs text-xs font-medium text-neutral transition hover:bg-neutral/10 hover:text-text"
        >
          <Server className="h-3.5 w-3.5" aria-hidden="true" />
          View Agents
        </button>
      </div>
    </div>
  );
}
