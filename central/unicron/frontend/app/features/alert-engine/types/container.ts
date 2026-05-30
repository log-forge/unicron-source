export interface ContainerInfo {
  identifier: string;
  name: string;
  host_id?: string;
  container_key: string;
  docker_container_id?: string | null;
  monitoring_enabled?: boolean;
  image_name: string;
  last_seen: string;
  /** Container status (running, exited, paused, etc.) */
  status?: string;
  /** Container labels (includes compose project, etc.) */
  labels?: Record<string, string>;
}

export interface GroupInfo {
  groupId: number | string;
  name: string;
  containerIds: string[];
  members?: { host_id: string; container_name: string }[];
  monitoredContainerCount?: number;
  monitoredContainers?: string[];
}
