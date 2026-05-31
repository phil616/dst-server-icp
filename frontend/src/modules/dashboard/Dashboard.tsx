import { Card, Col, Empty, Progress, Row, Statistic, Table, Tag } from "antd";
import type { ColumnsType } from "antd/es/table";
import { Link } from "react-router-dom";
import { useInstances } from "../../api/hooks";
import { StateTag } from "../../components/StateTag";

interface ShardRow {
  key: string;
  instanceId: number;
  instance: string;
  shard: string;
  port: number;
  state: string;
  pid: number | null;
  cpu: number | null;
  mem: number | null;
  players: string[];
}

export function Dashboard() {
  const { data: views = [], isLoading } = useInstances();

  const rows: ShardRow[] = views.flatMap((v) =>
    v.shards.map((s) => ({
      key: `${v.instance.cluster_dir_name}/${s.shard_dir_name}`,
      instanceId: v.instance.id,
      instance: v.instance.name,
      shard: s.shard_dir_name,
      port: s.server_port,
      state: s.runtime?.state ?? "stopped",
      pid: s.runtime?.pid ?? null,
      cpu: s.runtime?.resource?.cpu_percent ?? null,
      mem: s.runtime?.resource?.rss_mb ?? null,
      players: s.runtime?.players ?? [],
    })),
  );

  const runningShards = rows.filter((r) => ["ready", "running"].includes(r.state)).length;
  const totalPlayers = rows.reduce((n, r) => n + r.players.length, 0);
  const runningInstances = views.filter((v) =>
    v.shards.some((s) => ["ready", "running"].includes(s.runtime?.state ?? ""))).length;

  const columns: ColumnsType<ShardRow> = [
    { title: "实例", dataIndex: "instance",
      render: (t, r) => <Link to={`/instances/${r.instanceId}`}>{t}</Link> },
    { title: "Shard", dataIndex: "shard", render: (t) => <Tag>{t}</Tag> },
    { title: "端口", dataIndex: "port", width: 90 },
    { title: "状态", dataIndex: "state", width: 110, render: (s) => <StateTag state={s} /> },
    { title: "PID", dataIndex: "pid", width: 90, render: (p) => p ?? "—" },
    { title: "CPU", dataIndex: "cpu", width: 130,
      render: (c: number | null) => c == null ? "—"
        : <Progress percent={Math.min(100, Math.round(c))} size="small" style={{ width: 100 }} /> },
    { title: "内存", dataIndex: "mem", width: 100, render: (m) => (m == null ? "—" : `${m} MB`) },
    { title: "在线玩家", dataIndex: "players",
      render: (p: string[]) => p.length ? p.map((n) => <Tag key={n}>{n}</Tag>) : <span style={{ color: "#6b7787" }}>无</span> },
  ];

  return (
    <>
      <Row gutter={16} style={{ marginBottom: 16 }}>
        <Col span={6}><Card><Statistic title="实例总数" value={views.length} /></Card></Col>
        <Col span={6}><Card><Statistic title="运行中实例" value={runningInstances} valueStyle={{ color: "#52c41a" }} /></Card></Col>
        <Col span={6}><Card><Statistic title="运行中 Shard" value={runningShards} suffix={`/ ${rows.length}`} /></Card></Col>
        <Col span={6}><Card><Statistic title="在线玩家" value={totalPlayers} /></Card></Col>
      </Row>
      <Card title="Shard 运行状态" size="small">
        {rows.length === 0 && !isLoading
          ? <Empty description="暂无实例,去『实例管理』新建一个" />
          : <Table rowKey="key" size="small" loading={isLoading} dataSource={rows} columns={columns} pagination={false} />}
      </Card>
    </>
  );
}
