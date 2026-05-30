export function removeHostFromContainersCache<T extends ContainersCacheShape>(
  current: T | undefined,
  hostId: string,
): T | undefined {
  if (!current) return current;
  return {
    ...current,
    hosts: current.hosts.filter((host) => host.host_id !== hostId),
    containers: current.containers.filter((container) => (container.host_id || "local") !== hostId),
  };
}

type ContainersCacheShape = {
  hosts: Array<{ host_id: string }>;
  containers: Array<{ host_id?: string | null }>;
};
