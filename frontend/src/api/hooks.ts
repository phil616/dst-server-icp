import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as api from "./endpoints";
import type { AccessKind, BackupPolicy, CreateInstancePayload, Instance } from "./types";

// ---- 查询(带轮询,实时反映运行状态) ----
export const useInstances = () =>
  useQuery({ queryKey: ["instances"], queryFn: api.listInstances, refetchInterval: 4000 });

export const useInstance = (id: number) =>
  useQuery({
    queryKey: ["instance", id],
    queryFn: () => api.getInstance(id),
    refetchInterval: 3000,
    enabled: Number.isFinite(id) && id > 0,
  });

export const useShards = () =>
  useQuery({ queryKey: ["shards"], queryFn: api.listShards, refetchInterval: 3000 });

export const useJobs = () =>
  useQuery({ queryKey: ["jobs"], queryFn: api.listJobs, refetchInterval: 1500 });

export const useHealth = () =>
  useQuery({ queryKey: ["health"], queryFn: api.getHealth, refetchInterval: 60_000 });

export const useProxy = () =>
  useQuery({ queryKey: ["proxy"], queryFn: api.getProxy });

export const useBackups = (id: number) =>
  useQuery({ queryKey: ["backups", id], queryFn: () => api.listBackups(id), enabled: id > 0 });

// ---- 变更 ----
function useInvalidate() {
  const qc = useQueryClient();
  return (id?: number) => {
    qc.invalidateQueries({ queryKey: ["instances"] });
    qc.invalidateQueries({ queryKey: ["shards"] });
    if (id) qc.invalidateQueries({ queryKey: ["instance", id] });
  };
}

export const useCreateInstance = () => {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (p: CreateInstancePayload) => api.createInstance(p), onSuccess: () => inv() });
};

export const useImportInstance = () => {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (form: FormData) => api.importInstance(form), onSuccess: () => inv() });
};

export const useInstanceAction = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: "start" | "stop" | "force-stop" | "restart" }) =>
      action === "start" ? api.startInstance(id)
        : action === "stop" ? api.stopInstance(id)
        : action === "force-stop" ? api.stopInstance(id, false, true)  // 不保存、系统层 kill
        : api.restartInstance(id),
    onSuccess: (_d, v) => inv(v.id),
  });
};

export const useDeleteInstance = () => {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (id: number) => api.deleteInstance(id), onSuccess: () => inv() });
};

export const useSearchMods = () =>
  useMutation({ mutationFn: (q: string) => api.searchMods(q) });

export const useAddMod = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, workshop_id, name }: { id: number; workshop_id: string; name?: string }) =>
      api.addMod(id, { workshop_id, name }),
    onSuccess: (_d, v) => inv(v.id),
  });
};

export const useRemoveMod = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, workshopId }: { id: number; workshopId: string }) => api.removeMod(id, workshopId),
    onSuccess: (_d, v) => inv(v.id),
  });
};
export const useUpdateMod = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, workshopId, enabled, config }:
      { id: number; workshopId: string; enabled?: boolean; config?: Record<string, unknown> }) =>
      api.updateMod(id, workshopId, { enabled, config }),
    onSuccess: (_d, v) => inv(v.id),
  });
};
export const useCheckModUpdates = () => {
  const inv = useInvalidate();
  return useMutation({ mutationFn: (id: number) => api.checkModUpdates(id), onSuccess: (_d, id) => inv(id) });
};
export const useTriggerModsUpdate = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.triggerModsUpdate(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
};
export const useTriggerOneModUpdate = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, workshopId }: { id: number; workshopId: string }) => api.triggerOneModUpdate(id, workshopId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
};
export const useRepairLibrary = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.installRepairLibrary(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
};

/** 轮询作业直到结束,返回最终 Job。 */
export async function waitForJob(jobId: number, intervalMs = 1500, timeoutMs = 600000) {
  const end = Date.now() + timeoutMs;
  // eslint-disable-next-line no-constant-condition
  while (Date.now() < end) {
    const job = await api.getJob(jobId);
    if (job.status === "success" || job.status === "failed") return job;
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  return api.getJob(jobId);
}

export const useBackup = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, note }: { id: number; note?: string }) => api.createBackup(id, note),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ["backups", v.id] }),
  });
};

export const useSendCommand = () =>
  useMutation({
    mutationFn: ({ id, shard, command }: { id: number; shard: string; command: string }) =>
      api.sendCommand(id, shard, command),
  });

export const useUpdateShardPorts = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, shard, ports }: {
      id: number; shard: string;
      ports: { server_port?: number; master_server_port?: number; authentication_port?: number };
    }) => api.updateShardPorts(id, shard, ports),
    onSuccess: (_d, v) => inv(v.id),
  });
};

export const useInstall = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (kind: "steamcmd" | "server" | "mods") =>
      kind === "steamcmd" ? api.installSteamcmd()
        : kind === "server" ? api.installServer(true)
        : api.installMods(),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
};

export const useSaveProxy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: api.putProxy,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["proxy"] }),
  });
};

// ---- 配置更新 ----
export const useUpdateInstance = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Partial<Instance> }) => api.updateInstance(id, patch),
    onSuccess: (_d, v) => inv(v.id),
  });
};

// ---- 访问控制 ----
export const useAddAccess = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, kind, klei_id, note }: { id: number; kind: AccessKind; klei_id: string; note?: string }) =>
      api.addAccess(id, kind, klei_id, note),
    onSuccess: (_d, v) => inv(v.id),
  });
};
export const useRemoveAccess = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ id, kind, kleiId }: { id: number; kind: AccessKind; kleiId: string }) =>
      api.removeAccess(id, kind, kleiId),
    onSuccess: (_d, v) => inv(v.id),
  });
};

// ---- 存档 / 回滚 ----
export const useSaves = (id: number) =>
  useQuery({ queryKey: ["saves", id], queryFn: () => api.listSaves(id), enabled: id > 0, refetchInterval: 8000 });

export const useRollback = () =>
  useMutation({
    mutationFn: ({ id, shard, count }: { id: number; shard: string; count: number }) =>
      api.rollback(id, shard, count),
  });

// ---- 备份策略 / 还原 / 删除 ----
export const useBackupPolicy = () =>
  useQuery({ queryKey: ["backupPolicy"], queryFn: api.getBackupPolicy });
export const useSaveBackupPolicy = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (p: BackupPolicy) => api.putBackupPolicy(p),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["backupPolicy"] }),
  });
};
export const useRestoreBackup = () => {
  const inv = useInvalidate();
  return useMutation({
    mutationFn: ({ backupId, restart }: { backupId: number; restart: boolean }) =>
      api.restoreBackup(backupId, restart),
    onSuccess: () => inv(),
  });
};
export const useDeleteBackup = () => {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ backupId }: { backupId: number; instanceId: number }) => api.deleteBackup(backupId),
    onSuccess: (_d, v) => qc.invalidateQueries({ queryKey: ["backups", v.instanceId] }),
  });
};
