import { useEffect, useState } from "react";
import { useSocket } from "~/context/SocketContext";

export interface ContainerStats {
  container_key: string;
  cpu_percent: number;
  cpu_percent_host?: number;
  memory_usage: number;
  memory_limit: number;
  memory_percent: number;
  memory_percent_host?: number;
  network_rx_bytes: number;
  network_tx_bytes: number;
  network_rx_rate_bps?: number;
  network_tx_rate_bps?: number;
  block_read_bytes: number;
  block_write_bytes: number;
  block_read_bps?: number;
  block_write_bps?: number;
  timestamp: number;
}

export interface UseContainerStatsReturn {
  stats: ContainerStats | null;
  connected: boolean;
  loading: boolean;
  authError: boolean;
}

export function useContainerStats(
  containerKey: string,
  hostId: string
): UseContainerStatsReturn {
  const { socket } = useSocket();
  const [stats, setStats] = useState<ContainerStats | null>(null);
  const [connected, setConnected] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!socket || !containerKey || !hostId) {
      setConnected(false);
      setLoading(false);
      setStats(null);
      return;
    }

    const handleStats = (data: Record<string, unknown>) => {
      if (data.container_key !== containerKey) return;
      setStats(data as unknown as ContainerStats);
      setLoading(false);
    };
    const handleConnect = () => {
      setConnected(true);
      socket.emit("containers:stats:subscribe", { container_key: containerKey, host_id: hostId });
    };
    const handleDisconnect = () => setConnected(false);

    socket.on("containers:stats:data", handleStats);
    socket.on("connect", handleConnect);
    socket.on("disconnect", handleDisconnect);
    if (socket.connected) {
      handleConnect();
    }

    return () => {
      socket.emit("containers:stats:unsubscribe", { container_key: containerKey });
      socket.off("containers:stats:data", handleStats);
      socket.off("connect", handleConnect);
      socket.off("disconnect", handleDisconnect);
    };
  }, [socket, containerKey, hostId]);

  return { stats, connected, loading, authError: false };
}
