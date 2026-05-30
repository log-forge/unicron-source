export interface IHerald {
  herald_id: string;
  herald_name: string;
  central_url: string;
  registered_at: string | null;
  health_status: string;
  last_ping: string | null;
  health_message: string | null;
  check_in_interval: number | null;
  region: string | null;
  tags: string[];
  socket_online: boolean;
  socket_last_seen: string | null;
  herald_version: string | null;
  hostname: string | null;
  herald_os: string | null;
  os_version: string | null;
  architecture: string | null;
  cpu_count: number | null;
  host_total_memory_bytes: number | null;
}

export interface IHeraldsSummary {
  total: number;
  statuses: Record<string, number>;
  last_ping_latest: string | null;
  socket_online_total: number;
  groups: Record<string, number>;
  regions: Record<string, number>;
}
