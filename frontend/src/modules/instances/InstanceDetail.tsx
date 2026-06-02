import { ArrowLeftOutlined } from "@ant-design/icons";
import {
  Button, Card, Descriptions, Popconfirm, Space, Spin, Table, Tag, Tooltip, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useBackup, useDeleteInstance, useInstance, useInstanceAction } from "../../api/hooks";
import type { Shard } from "../../api/types";
import { StateTag } from "../../components/StateTag";
import { AccessControl } from "../access/AccessControl";
import { BackupsPanel } from "../backups/BackupsPanel";
import { ConfigForm } from "../config/ConfigForm";
import { ShardPortsForm } from "../config/ShardPortsForm";
import { ModManager } from "../mods/ModManager";
import { Console } from "./Console";

export function InstanceDetail() {
  const { id } = useParams();
  const instanceId = Number(id);
  const navigate = useNavigate();
  const { data: view, isLoading } = useInstance(instanceId);
  const action = useInstanceAction();
  const del = useDeleteInstance();
  const backup = useBackup();
  const [tab, setTab] = useState("overview");

  if (isLoading || !view) return <Spin />;
  const { instance, shards, mods, access } = view;

  const run = async (act: "start" | "stop" | "force-stop" | "restart") => {
    try { await action.mutateAsync({ id: instanceId, action: act }); message.success("已操作"); }
    catch (e) { message.error((e as Error).message); }
  };

  const shardCols: ColumnsType<Shard> = [
    { title: "Shard", dataIndex: "shard_dir_name", render: (t, r) => <Tag color={r.is_master ? "gold" : "default"}>{t}</Tag> },
    { title: "状态", render: (_, r) => <StateTag state={r.runtime?.state ?? "stopped"} /> },
    { title: "PID", render: (_, r) => r.runtime?.pid ?? "—" },
    { title: "玩家端口", dataIndex: "server_port" },
    { title: "CPU", render: (_, r) => (r.runtime?.resource ? `${r.runtime.resource.cpu_percent}%` : "—") },
    { title: "内存", render: (_, r) => (r.runtime?.resource ? `${r.runtime.resource.rss_mb} MB` : "—") },
    { title: "预设", dataIndex: "worldgen_preset" },
    {
      title: "在线玩家", render: (_, r) => {
        const players = r.runtime?.players ?? [];
        if (!players.length) return "—";
        const ids = r.runtime?.player_ids ?? {};
        return (
          <Space size={[4, 4]} wrap>
            {players.map((p) => (
              ids[p]
                ? <Tooltip key={p} title={`Klei ID：${ids[p]}（已自动记入通讯录）`}>
                    <Tag color="green">{p}</Tag>
                  </Tooltip>
                : <Tag key={p}>{p}</Tag>
            ))}
          </Space>
        );
      },
    },
  ];

  const overview = (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Descriptions bordered size="small" column={2}>
        <Descriptions.Item label="名称">{instance.name}</Descriptions.Item>
        <Descriptions.Item label="Cluster 目录">{instance.cluster_dir_name}</Descriptions.Item>
        <Descriptions.Item label="模式">{instance.game_mode}</Descriptions.Item>
        <Descriptions.Item label="网络">{instance.online ? "在线" : "离线"}</Descriptions.Item>
        <Descriptions.Item label="人数上限">{instance.max_players}</Descriptions.Item>
        <Descriptions.Item label="PVP">{instance.pvp ? "是" : "否"}</Descriptions.Item>
        <Descriptions.Item label="master_port">{instance.master_port}</Descriptions.Item>
        <Descriptions.Item label="Token">{instance.has_token ? "已配置" : "无"}</Descriptions.Item>
      </Descriptions>
      <Table rowKey="id" size="small" dataSource={shards} columns={shardCols} pagination={false} />
    </Space>
  );

  const contents: Record<string, React.ReactNode> = {
    overview,
    config: (
      <Space direction="vertical" size="middle" style={{ width: "100%" }}>
        <ConfigForm instance={instance} />
        <ShardPortsForm instanceId={instanceId} shards={shards} />
      </Space>
    ),
    access: <AccessControl instance={instance} access={access} />,
    mods: <ModManager instanceId={instanceId} mods={mods} />,
    backups: <BackupsPanel instance={instance} />,
    console: <Console instanceId={instanceId} cluster={instance.cluster_dir_name} shards={shards} />,
  };

  return (
    <Card
      title={
        <Space>
          <Link to="/instances"><Button type="text" icon={<ArrowLeftOutlined />} /></Link>
          {instance.name}
          <StateTag state={instance.status} />
        </Space>
      }
      extra={
        <Space wrap>
          <Button type="primary" onClick={() => run("start")}>启动</Button>
          <Button danger onClick={() => run("stop")}>停止</Button>
          <Popconfirm
            title="强制停止?"
            description="将跳过存档、直接从系统层 kill 掉 Master 与所有 Caves 进程,未保存的进度会丢失。"
            okText="强制停止" okButtonProps={{ danger: true }} cancelText="取消"
            onConfirm={() => run("force-stop")}>
            <Button danger>强制停止</Button>
          </Popconfirm>
          <Button onClick={() => run("restart")}>重启</Button>
          <Button loading={backup.isPending}
            onClick={async () => { await backup.mutateAsync({ id: instanceId, note: "手动" }); message.success("已备份"); }}>
            备份
          </Button>
          <Popconfirm title="删除实例及其存档?" okButtonProps={{ danger: true }}
            onConfirm={async () => { await del.mutateAsync(instanceId); message.success("已删除"); navigate("/instances"); }}>
            <Button danger>删除</Button>
          </Popconfirm>
        </Space>
      }
      tabList={[
        { key: "overview", tab: "概览" },
        { key: "config", tab: "配置" },
        { key: "access", tab: `访问控制 (${access.length})` },
        { key: "mods", tab: `MOD 管理 (${mods.length})` },
        { key: "backups", tab: "备份与存档" },
        { key: "console", tab: "控制台 / 日志" },
      ]}
      activeTabKey={tab}
      onTabChange={setTab}
    >
      {contents[tab]}
    </Card>
  );
}
