export interface ILogMsgJson {
  log?: string | null;
  stream?: string | null;
  time?: string | null;
}

export interface ILogRow {
  time?: string | null;
  _time?: string | null;
  stream_id?: string | null;
  _stream_id?: string | null;
  stream?: string | null;
  _stream?: string | null;
  msg?: string | null;
  _msg?: string | null;
  msg_json?: ILogMsgJson | null;

  collector_role?: string | null;
  docker_container_id?: string | null;
  container_key?: string | null;
  container_name?: string | null;
  herald_env?: string | null;
  herald_id?: string | null;
  herald_name?: string | null;
  image_name?: string | null;
  image_tag?: string | null;
  service_instance_id?: string | null;
  service_name?: string | null;
  service_namespace?: string | null;
  severity?: string | null;

  [key: string]: unknown;
}
