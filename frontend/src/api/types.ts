// 与后端 JSON 形状对应的类型(见 src/dst_serverd/models.py / supervisor）。

export type ShardState =
  | "stopped" | "starting" | "running" | "ready" | "stopping" | "crashed" | "created";

export interface ProcResource {
  pid: number;
  cpu_percent: number;
  rss_mb: number;
  num_threads: number;
  status: string;
  create_time: number;
}

export interface LoadedMod {
  name: string;
  version: string;
  status: string; // loaded | failed
}

export interface ShardRuntime {
  key: string;
  cluster: string;
  shard: string;
  state: ShardState;
  pid: number | null;
  ready: boolean;
  desired_running: boolean;
  players: string[];
  player_ids: Record<string, string>; // 昵称 -> KU_(日志就近配对到的,可能缺失)
  loaded_mods: Record<string, LoadedMod>;
  resource: ProcResource | null;
}

/** 本地通讯录条目:玩家加入即自动记忆的 昵称↔Klei ID。 */
export interface Contact {
  klei_id: string;
  name: string;
  note: string;
  first_seen: number;
  last_seen: number;
  seen_count: number;
}

export interface Shard {
  id: number;
  instance_id: number;
  role: string;
  shard_dir_name: string;
  is_master: boolean;
  server_port: number;
  master_server_port: number;
  authentication_port: number;
  worldgen_preset: string;
  runtime: ShardRuntime | null;
}

export interface Instance {
  id: number;
  name: string;
  cluster_dir_name: string;
  online: boolean;
  game_mode: string;
  pvp: boolean;
  max_players: number;
  max_snapshots: number;
  pause_when_empty: boolean;
  cluster_password: string;
  cluster_intention: string;
  cluster_description: string;
  server_language: string;
  cluster_language: string;
  cluster_key: string;
  master_port: number;
  token: string;
  has_token: boolean;
  tick_rate: number;
  vote_enabled: boolean;
  autosaver_enabled: boolean;
  whitelist_slots: number;
  lan_only_cluster: boolean;
  created_at: number;
  desired_status: string;
  status: ShardState;
}

export type AccessKind = "admin" | "whitelist" | "blocklist";

export interface AccessEntry {
  id: number;
  instance_id: number;
  kind: AccessKind;
  klei_id: string;
  note: string;
}

export interface SessionInfo {
  session_id: string;
  files: number;
  size: number;
  mtime: number;
}

export interface ShardSave {
  shard: string;
  exists: boolean;
  size: number;
  sessions: SessionInfo[];
  snapshot_files: number;
}

export interface SaveInfo {
  max_snapshots: number;
  shards: ShardSave[];
}

export interface BackupPolicy {
  auto_enabled: boolean;
  interval_min: number;
  retention: number;
}

export type ModUpdateStatus = "latest" | "outdated" | "unknown" | "unchecked" | "manual";

export interface ModConfigChoice {
  description: string;
  hover: string;
  data: unknown;
}

export interface ModConfigOption {
  name: string;
  label: string;
  hover: string;
  has_default: boolean;
  default: unknown;
  options: ModConfigChoice[];
}

export interface ModConfigSchema {
  installed: boolean;
  info: Record<string, unknown>;
  options: ModConfigOption[];
  error: string;
}

export interface ModConfigTranslation {
  labels: Record<string, string>;
  choices: Record<string, Record<string, string>>;
  guidance: ModConfigGuidance | null;
}

export interface ModConfigGuidance {
  summary: string;
  details: string[];
  manual_steps: string[];
  files: { path: string; purpose: string }[];
  warnings: string[];
}

export interface Mod {
  id: number;
  instance_id: number;
  workshop_id: string;
  name: string;
  enabled: boolean;
  source: string;
  ref: string;
  config: Record<string, unknown>;
  config_schema: ModConfigSchema;
  title: string;
  installed_time_updated: number;
  workshop_time_updated: number;
  last_checked: number;
  update_status: ModUpdateStatus;
  loaded: Record<string, LoadedMod>; // shard_dir_name -> 加载信息
}

export interface InstanceView {
  instance: Instance;
  shards: Shard[];
  mods: Mod[];
  access: AccessEntry[];
}

export interface WorkshopSearchResult {
  workshop_id: string;
  title: string;
  time_updated: number;
  file_size: number;
  preview_url: string;
}

export interface Job {
  id: number;
  action: string;
  status: "queued" | "running" | "success" | "failed" | "canceled";
  returncode: number | null;
  error: string;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
}

export interface Backup {
  id: number;
  instance_id: number;
  type: string;
  trigger: string;
  path: string;
  size: number;
  created_at: number;
  note: string;
}

export interface ProxyCfg {
  enabled: boolean;
  mode: string;
  scheme: string;
  host: string;
  port: number;
  username: string;
  password: string;
  no_proxy: string;
  active: boolean;
}

export interface AiSettings {
  api_base: string;
  api_key: string;
  model: string;
}

export interface CreateInstancePayload {
  name: string;
  online: boolean;
  token: string;
  game_mode: string;
  pvp: boolean;
  max_players: number;
  caves: boolean;
  cluster_intention?: string;
  cluster_password?: string;
  cluster_description?: string;
  server_language?: string;
  cluster_language?: string;
}
