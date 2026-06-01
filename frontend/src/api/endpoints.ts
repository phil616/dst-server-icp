import { http } from "./client";
import type {
  AccessEntry, AccessKind, Backup, BackupPolicy, CreateInstancePayload, Instance,
  InstanceView, Job, Mod, ProxyCfg, SaveInfo, ShardRuntime, WorkshopSearchResult,
} from "./types";

// ---- 鉴权 ----
export const authRequired = () =>
  http.get<{ required: boolean }>("/api/auth/required").then((r) => r.data);
export const verifyApiKey = () =>
  http.get<{ ok: boolean }>("/api/auth/verify").then((r) => r.data);

// ---- 实例 ----
export const listInstances = () =>
  http.get<InstanceView[]>("/api/instances").then((r) => r.data);
export const getInstance = (id: number) =>
  http.get<InstanceView>(`/api/instances/${id}`).then((r) => r.data);
export const createInstance = (p: CreateInstancePayload) =>
  http.post<InstanceView>("/api/instances", p).then((r) => r.data);
export const importInstance = (form: FormData) =>
  http.post<InstanceView>("/api/instances/import", form).then((r) => r.data);
export const deleteInstance = (id: number) =>
  http.delete(`/api/instances/${id}`).then((r) => r.data);
export const startInstance = (id: number) =>
  http.post(`/api/instances/${id}/start`).then((r) => r.data);
export const stopInstance = (id: number, save = true, force = false) =>
  http.post(`/api/instances/${id}/stop?save=${save}&force=${force}`).then((r) => r.data);
export const restartInstance = (id: number) =>
  http.post(`/api/instances/${id}/restart`).then((r) => r.data);
export const updateInstance = (id: number, patch: Partial<Instance>) =>
  http.patch<InstanceView>(`/api/instances/${id}`, patch).then((r) => r.data);
export const getRawConfig = (id: number) =>
  http.get(`/api/instances/${id}/config/raw`).then((r) => r.data);
export const sendCommand = (id: number, shard: string, command: string) =>
  http.post(`/api/instances/${id}/shards/${shard}/command`, { command }).then((r) => r.data);
export const updateShardPorts = (
  id: number, shard: string,
  ports: { server_port?: number; master_server_port?: number; authentication_port?: number },
) => http.patch<InstanceView>(`/api/instances/${id}/shards/${shard}/ports`, ports).then((r) => r.data);
export const rollback = (id: number, shard: string, count: number) =>
  http.post(`/api/instances/${id}/shards/${shard}/rollback?count=${count}`).then((r) => r.data);

// ---- 访问控制 ----
export const listAccess = (id: number) =>
  http.get<AccessEntry[]>(`/api/instances/${id}/access`).then((r) => r.data);
export const addAccess = (id: number, kind: AccessKind, klei_id: string, note = "") =>
  http.post<AccessEntry>(`/api/instances/${id}/access`, { kind, klei_id, note }).then((r) => r.data);
export const removeAccess = (id: number, kind: AccessKind, kleiId: string) =>
  http.delete(`/api/instances/${id}/access/${kind}/${kleiId}`).then((r) => r.data);

// ---- 存档 / 回滚 ----
export const listSaves = (id: number) =>
  http.get<SaveInfo>(`/api/instances/${id}/saves`).then((r) => r.data);

// ---- 全局 Shard 进程 ----
export const listShards = () =>
  http.get<ShardRuntime[]>("/api/shards").then((r) => r.data);

// ---- MOD ----
export const searchMods = (q: string) =>
  http.get<{ results: WorkshopSearchResult[] }>(`/api/mods/search?q=${encodeURIComponent(q)}`)
    .then((r) => r.data.results);
export const addMod = (id: number, body: Partial<Mod> & { workshop_id: string }) =>
  http.post<Mod>(`/api/instances/${id}/mods`, body).then((r) => r.data);
export const updateMod = (id: number, workshopId: string, body: { enabled?: boolean; config?: Record<string, unknown> }) =>
  http.patch<Mod>(`/api/instances/${id}/mods/${workshopId}`, body).then((r) => r.data);
export const removeMod = (id: number, workshopId: string) =>
  http.delete(`/api/instances/${id}/mods/${workshopId}`).then((r) => r.data);
export const checkModUpdates = (id: number) =>
  http.post<InstanceView>(`/api/instances/${id}/mods/check-updates`).then((r) => r.data);
export const triggerModsUpdate = (id: number) =>
  http.post<Job>(`/api/instances/${id}/mods/update`).then((r) => r.data);
export const triggerOneModUpdate = (id: number, workshopId: string) =>
  http.post<Job>(`/api/instances/${id}/mods/${workshopId}/update`).then((r) => r.data);

// ---- 备份 ----
export const listBackups = (id: number) =>
  http.get<Backup[]>(`/api/instances/${id}/backups`).then((r) => r.data);
export const createBackup = (id: number, note = "") =>
  http.post<Backup>(`/api/instances/${id}/backups`, { note }).then((r) => r.data);
export const restoreBackup = (backupId: number, restart: boolean) =>
  http.post(`/api/backups/${backupId}/restore?restart=${restart}`).then((r) => r.data);
export const deleteBackup = (backupId: number) =>
  http.delete(`/api/backups/${backupId}`).then((r) => r.data);
export const downloadBackupUrl = (backupId: number) => `/api/backups/${backupId}/download`;
export const getBackupPolicy = () =>
  http.get<BackupPolicy>("/api/settings/backup").then((r) => r.data);
export const putBackupPolicy = (p: BackupPolicy) =>
  http.put<BackupPolicy>("/api/settings/backup", p).then((r) => r.data);

// ---- 安装/更新 + 作业 ----
export const installSteamcmd = (force = false) =>
  http.post<Job>(`/api/install/steamcmd?force=${force}`).then((r) => r.data);
export const installServer = (validate_files: boolean) =>
  http.post<Job>("/api/install/server", { validate_files }).then((r) => r.data);
export const installMods = () =>
  http.post<Job>("/api/install/mods").then((r) => r.data);
export const installRepairLibrary = () =>
  http.post<Job>("/api/install/repair-library").then((r) => r.data);
export const listJobs = () => http.get<Job[]>("/api/jobs").then((r) => r.data);
export const getJob = (jobId: number) => http.get<Job>(`/api/jobs/${jobId}`).then((r) => r.data);
export const getActivity = (lines = 400) =>
  http.get<{ lines: string[] }>(`/api/activity?lines=${lines}`).then((r) => r.data);

// ---- 健康 / 版本 ----
export const getHealth = () =>
  http.get<{ status: string; version: string; python: string; platform: string }>("/api/health").then((r) => r.data);

// ---- 代理 ----
export const getProxy = () => http.get<ProxyCfg>("/api/proxy").then((r) => r.data);
export const putProxy = (cfg: Partial<ProxyCfg>) =>
  http.put<ProxyCfg>("/api/proxy", cfg).then((r) => r.data);
