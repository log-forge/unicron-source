export type HeraldRegisterEventSuccessData = {
  herald_id: string;
  herald_name: string;
  central_url?: string;
  group?: string;
  tags?: string[];
  status?: "healthy";
};

export type HeraldRegisterFailureDetail = {
  code: string;
  message?: string | null;
};

export type HeraldRegisterEventFailData = {
  herald_id: string;
  herald_name: string;
  status: "failed";
  reason?: string;
  failure?: HeraldRegisterFailureDetail | null;
};

export type HeraldRegisterEventData = HeraldRegisterEventSuccessData | HeraldRegisterEventFailData;

export interface IHeraldHealthEventPayload {
  herald_id: string;
  herald_name: string;
  status: string;
  message?: string | null;
  last_ping?: string | null;
  registered_at?: string | null;
  check_in_interval?: number | null;
  socket_online?: boolean;
  socket_last_seen?: string | null;
  region?: string | null;
  tags?: string[];
  central_url?: string | null;
  herald_version?: string | null;
  hostname?: string | null;
  herald_os?: string | null;
  os_version?: string | null;
  architecture?: string | null;
  cpu_count?: number | null;
  host_total_memory_bytes?: number | null;
}
