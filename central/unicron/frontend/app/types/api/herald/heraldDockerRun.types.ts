export interface IDockerRunRequest {
  host_url: string;
  mtls_port?: number | null; // default 8443
  herald_name?: string | null;
  herald_cert_subjects?: string | null; // comma separated
  herald_port?: number | null; // default 9443
  check_in_interval?: number | null;
  selinux_relabel?: boolean | null;
  // metadata fields
  region?: string | null; // e.g. "us-west-1"
  group?: string | null;
  tags?: string[] | null;
}

export interface IDockerRunResponse {
  ok: boolean;
  command: string;
  herald_name?: string | null;
  herald_id?: string | null;
  partial_success?: boolean | null;
  error?: string | null;
}
