import { useEffect, useState } from "react";
import { AlertTriangle } from "lucide-react";
import { useSocket } from "~/context/SocketContext";

interface TelemetryHealthState {
  [hostId: string]: boolean;
}

export function TelemetryBanner() {
  const [healthStates, setHealthStates] = useState<TelemetryHealthState>({});
  const { socket } = useSocket();

  useEffect(() => {
    if (!socket) return;

    const handleTelemetryHealth = (data: { host_id?: string; healthy?: boolean }) => {
      const hostId = data?.host_id;
      if (!hostId) return;
      setHealthStates((prev) => ({
        ...prev,
        [hostId]: Boolean(data.healthy),
      }));
    };

    socket.on("containers:telemetry_health", handleTelemetryHealth);
    return () => {
      socket.off("containers:telemetry_health", handleTelemetryHealth);
    };
  }, [socket]);

  const unhealthyHosts = Object.entries(healthStates)
    .filter(([, healthy]) => !healthy)
    .map(([hostId]) => hostId);

  if (unhealthyHosts.length === 0) return null;

  return (
    <div className="bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800 rounded-lg px-4 py-3 mb-4 flex items-center gap-3">
      <AlertTriangle className="h-5 w-5 text-amber-500 flex-shrink-0" />
      <p className="text-sm text-amber-800 dark:text-amber-200">
        Telemetry pipeline unhealthy on{" "}
        {unhealthyHosts.length === 1 ? unhealthyHosts[0] : `${unhealthyHosts.length} hosts`}
      </p>
    </div>
  );
}
