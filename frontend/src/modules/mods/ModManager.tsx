import { CloudSyncOutlined, DeleteOutlined, PlusOutlined, ReloadOutlined, ToolOutlined } from "@ant-design/icons";
import {
  Alert, Button, Descriptions, Popconfirm, Space, Switch, Table, Tag, Tooltip, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useState } from "react";
import {
  useCheckModUpdates, useRemoveMod, useRepairLibrary, useTriggerModsUpdate,
  useTriggerOneModUpdate, useUpdateMod, waitForJob,
} from "../../api/hooks";
import type { Mod, ModUpdateStatus } from "../../api/types";
import { ModSearchModal } from "./ModSearchModal";

const UPDATE_TAG: Record<ModUpdateStatus, { color: string; text: string }> = {
  latest: { color: "success", text: "最新" },
  outdated: { color: "error", text: "有更新" },
  unknown: { color: "default", text: "未知(请更新一次)" },
  unchecked: { color: "default", text: "未检查" },
  manual: { color: "blue", text: "手动 MOD" },
};

/** 版本号格式化:纯数字版本(如 1.2.3)加 "v" 前缀;含空格/字母的字符串版本(部分 MOD 把
 *  整串塞进 modinfo 的 version 字段,如 "under the weather pt.1 v1.5.4.1")原样显示,不再被截断。 */
function fmtVersion(v: string): string {
  const s = (v || "").trim();
  if (!s) return "—";
  return /^\d/.test(s) ? `v${s}` : s;
}

/** 过长的版本号在标签里截断显示,完整内容交给 Tooltip 悬停展示。 */
function shortVersion(v: string, max = 14): string {
  const s = fmtVersion(v);
  return s.length > max ? `${s.slice(0, max).trimEnd()} …` : s;
}

/** MOD 管理:增删 / 启停 / 看配置 / 检查更新 / 一键更新 / 确认是否真正加载到游戏。 */
export function ModManager({ instanceId, mods }: { instanceId: number; mods: Mod[] }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const remove = useRemoveMod();
  const update = useUpdateMod();
  const check = useCheckModUpdates();
  const triggerUpdate = useTriggerModsUpdate();
  const triggerOne = useTriggerOneModUpdate();
  const repair = useRepairLibrary();

  const hasUpdates = mods.some((m) => m.update_status === "outdated");
  const existingIds = new Set(mods.map((m) => m.workshop_id));

  const doCheck = async () => {
    try { await check.mutateAsync(instanceId); message.success("已检查更新"); }
    catch (e) { message.error((e as Error).message); }
  };
  const doUpdate = async () => {
    try {
      const j = await triggerUpdate.mutateAsync(instanceId);
      message.info(`更新作业 #${j.id} 进行中…(缺 Steam 库会自动修复;实时输出见“系统日志”)`);
      const done = await waitForJob(j.id);
      if (done.status === "success") message.success("MOD 更新成功");
      else message.error(`MOD 更新失败:${done.error || "见系统日志"}`, 8);
    } catch (e) { message.error((e as Error).message); }
  };

  const doUpdateOne = async (wid: string) => {
    try {
      const j = await triggerOne.mutateAsync({ id: instanceId, workshopId: wid });
      message.info(`MOD ${wid} 更新作业 #${j.id} 进行中…`);
      const done = await waitForJob(j.id);
      if (done.status === "success") message.success(`MOD ${wid} 更新成功`);
      else message.error(`MOD ${wid} 更新失败:${done.error || "见系统日志"}`, 8);
    } catch (e) { message.error((e as Error).message); }
  };

  const doRepair = async () => {
    try {
      const j = await repair.mutateAsync();
      message.info(`修复作业 #${j.id} 进行中…(SteamCMD 校验安装,可能较久)`);
      const done = await waitForJob(j.id);
      if (done.status === "success") message.success("Steam 库已修复/校验完成");
      else message.error(`修复失败:${done.error || "见系统日志"}`, 8);
    } catch (e) { message.error((e as Error).message); }
  };

  const columns: ColumnsType<Mod> = [
    {
      title: "MOD", render: (_, m) => (
        <Space direction="vertical" size={0}>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>{m.ref}</Tag>
          <span>{m.title || m.name || "—"}</span>
        </Space>
      ),
    },
    {
      title: "已加载到游戏", render: (_, m) => {
        const shards = Object.entries(m.loaded);
        if (!shards.length) return <Tag color="default">未加载</Tag>;
        return shards.map(([shard, info]) => (
          <Tooltip key={shard} title={`${info.name} ${fmtVersion(info.version)}`}>
            <Tag color={info.status === "loaded" ? "success" : "error"}>
              {shard}: {info.status === "loaded" ? `✓ ${shortVersion(info.version)}` : "✗ 失败"}
            </Tag>
          </Tooltip>
        ));
      },
    },
    {
      title: "更新状态", render: (_, m) => {
        const t = UPDATE_TAG[m.update_status];
        const when = m.workshop_time_updated
          ? dayjs.unix(m.workshop_time_updated).format("YYYY-MM-DD") : "";
        return <Tooltip title={when && `Workshop 最近更新:${when}`}><Tag color={t.color}>{t.text}</Tag></Tooltip>;
      },
    },
    { title: "配置项", render: (_, m) => Object.keys(m.config).length || 0 },
    { title: "启用", render: (_, m) => <Switch checked={m.enabled} size="small"
        onChange={async (v) => { try { await update.mutateAsync({ id: instanceId, workshopId: m.workshop_id, enabled: v }); } catch (e) { message.error((e as Error).message); } }} /> },
    {
      title: "操作", width: 150, render: (_, m) => (
        <Space>
          {m.update_status === "outdated" &&
            <Button size="small" type="primary" icon={<CloudSyncOutlined />}
              onClick={() => doUpdateOne(m.workshop_id)}>更新</Button>}
          <Popconfirm title="移除该 MOD?"
            onConfirm={async () => { await remove.mutateAsync({ id: instanceId, workshopId: m.workshop_id }); message.success("已移除"); }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Alert type="info" banner
        message="“已加载到游戏”来自服务器日志的 Loading mod 行(需服务器运行,确认真正载入而非仅下载完成);“更新状态”经 Steam Workshop API 比对更新时间。更新前会自动预检并修复 Steam 库(解决 “library folder not found” 导致的下载失败),成功/失败均有提示。" />
      <Space wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setSearchOpen(true)}>搜索添加 MOD</Button>
        <Button icon={<ReloadOutlined />} loading={check.isPending} onClick={doCheck}>检查更新</Button>
        <Button type="primary" ghost danger={hasUpdates} icon={<CloudSyncOutlined />}
          loading={triggerUpdate.isPending} onClick={doUpdate}>
          {hasUpdates ? "更新全部(有新版)" : "更新全部(自动修复)"}
        </Button>
        <Tooltip title="单独校验/修复 Steam 库与服务端安装(SteamCMD validate)。当出现 “library folder not found” 或下载一直失败时使用。">
          <Button icon={<ToolOutlined />} loading={repair.isPending} onClick={doRepair}>修复 Steam 库</Button>
        </Tooltip>
      </Space>
      <Table
        rowKey="id" size="small" dataSource={mods} columns={columns} pagination={false}
        locale={{ emptyText: "暂无 MOD" }}
        expandable={{
          rowExpandable: (m) => Object.keys(m.config).length > 0,
          expandedRowRender: (m) => (
            <Descriptions size="small" column={2} bordered title="configuration_options">
              {Object.entries(m.config).map(([k, v]) => (
                <Descriptions.Item key={k} label={k}>{String(v)}</Descriptions.Item>
              ))}
            </Descriptions>
          ),
        }}
      />
      <ModSearchModal instanceId={instanceId} existingIds={existingIds}
        open={searchOpen} onClose={() => setSearchOpen(false)} />
    </Space>
  );
}
