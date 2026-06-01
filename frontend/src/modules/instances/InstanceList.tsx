import { ImportOutlined, PlusOutlined } from "@ant-design/icons";
import { Button, Card, Popconfirm, Space, Table, Tag, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useDeleteInstance, useInstanceAction, useInstances } from "../../api/hooks";
import type { InstanceView } from "../../api/types";
import { StateTag } from "../../components/StateTag";
import { CreateInstanceModal } from "./CreateInstanceModal";
import { ImportInstanceModal } from "./ImportInstanceModal";

export function InstanceList() {
  const { data: views = [], isLoading } = useInstances();
  const action = useInstanceAction();
  const del = useDeleteInstance();
  const [createOpen, setCreateOpen] = useState(false);
  const [importOpen, setImportOpen] = useState(false);

  const run = async (id: number, act: "start" | "stop" | "force-stop" | "restart") => {
    try { await action.mutateAsync({ id, action: act }); message.success(`已${{ start: "启动", stop: "停止", "force-stop": "强制停止", restart: "重启" }[act]}`); }
    catch (e) { message.error((e as Error).message); }
  };

  const columns: ColumnsType<InstanceView> = [
    { title: "名称", render: (_, v) => <Link to={`/instances/${v.instance.id}`}>{v.instance.name}</Link> },
    { title: "Cluster 目录", render: (_, v) => <Tag>{v.instance.cluster_dir_name}</Tag> },
    { title: "模式", render: (_, v) => v.instance.game_mode },
    { title: "网络", render: (_, v) => (v.instance.online ? "在线" : "离线") },
    { title: "状态", render: (_, v) => <StateTag state={v.instance.status} /> },
    {
      title: "Shard", render: (_, v) => {
        const up = v.shards.filter((s) => ["ready", "running"].includes(s.runtime?.state ?? "")).length;
        return `${up}/${v.shards.length} 在跑`;
      },
    },
    {
      title: "操作", width: 320, render: (_, v) => (
        <Space wrap>
          <Button size="small" type="primary" onClick={() => run(v.instance.id, "start")}>启动</Button>
          <Button size="small" danger onClick={() => run(v.instance.id, "stop")}>停止</Button>
          <Popconfirm
            title="强制停止?"
            description="将跳过存档、直接从系统层 kill 掉 Master 与所有 Caves 进程,未保存的进度会丢失。"
            okText="强制停止" okButtonProps={{ danger: true }} cancelText="取消"
            onConfirm={() => run(v.instance.id, "force-stop")}>
            <Button size="small" danger>强制停止</Button>
          </Popconfirm>
          <Button size="small" onClick={() => run(v.instance.id, "restart")}>重启</Button>
          <Link to={`/instances/${v.instance.id}`}><Button size="small">详情</Button></Link>
          <Popconfirm title="删除实例及其存档?" okButtonProps={{ danger: true }}
            onConfirm={async () => { await del.mutateAsync(v.instance.id); message.success("已删除"); }}>
            <Button size="small" danger>删除</Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card title="实例管理"
      extra={
        <Space>
          <Button icon={<ImportOutlined />} onClick={() => setImportOpen(true)}>导入存档</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => setCreateOpen(true)}>新建实例</Button>
        </Space>
      }>
      <Table rowKey={(v) => v.instance.id} size="small" loading={isLoading} dataSource={views} columns={columns} pagination={false} />
      <CreateInstanceModal open={createOpen} onClose={() => setCreateOpen(false)} />
      <ImportInstanceModal open={importOpen} onClose={() => setImportOpen(false)} />
    </Card>
  );
}
