// Shared types for Herald inventory telemetry with Central backend and frontend
export interface IHeraldInventoryRecord {
  herald_id: string;
  herald_name: string;
  central_url: string;
  registered_at: string | null;
  health_status: string;
  last_ping: string | null;
  health_message: string | null;
  check_in_interval: number;
  region: string | null;
  tags: string[];
  socket_online: boolean;
  socket_last_seen: string | null;
  hostname: string | null;
  herald_os: string | null;
  os_version: string | null;
  architecture: string | null;
  cpu_count: number | null;
  host_total_memory_bytes: number | null;
  herald_version: string | null;
}

export interface IContainerInventoryRecord {
  name: string;
  container_key: string;
  docker_container_id: string | null;
  status: string | null;
  started_at: string | null;
  monitoring_enabled: boolean;
  group: string | null;
  image: string | null;
  image_id: string | null;
  labels: Record<string, string>;
  cpu_limit: number | null;
  memory_limit_bytes: number | null;
  restart_policy: string | null;
  created_at: string | null;
  command: string | null;
  entrypoint: string | null;
  working_dir: string | null;
  environment: string[];
  mounts: Array<Record<string, unknown>>;
  ports: Record<string, Array<{ HostIp: string | null; HostPort: string | null }>>;
  networks: Record<string, Record<string, unknown>>;
}

export interface IInventorySnapshotResponse {
  generated_at: string;
  heralds: IHeraldInventoryRecord[];
  containers: IContainerInventoryRecord[];
}
