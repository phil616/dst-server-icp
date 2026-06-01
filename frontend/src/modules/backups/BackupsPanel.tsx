import { CloudUploadOutlined, DeleteOutlined, DownloadOutlined, RollbackOutlined } from "@ant-design/icons";
import {
  Alert, Button, Card, Col, Descriptions, InputNumber, Popconfirm, Row, Space, Switch,
  Table, Tag, Tooltip, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import { downloadBackupUrl } from "../../api/endpoints";
import {
  useBackup, useBackupPolicy, useBackups, useDeleteBackup, useRestoreBackup,
  useRollback, useSaveBackupPolicy, useSaves,
} from "../../api/hooks";
import type { Backup, Instance } from "../../api/types";

function fmtSize(n: number) { return n >= 1 << 20 ? `${(n / (1 << 20)).toFixed(1)} MB` : `${(n / 1024).toFixed(1)} KB`; }

/** 存档与备份模块:快照回滚 + 文件级备份/还原/下载 + 自动备份策略。 */
export function BackupsPanel({ instance }: { instance: Instance }) {
  const id = instance.id;
  const { data: saves } = useSaves(id);
  const { data: backups = [], refetch } = useBackups(id);
  const backup = useBackup();
  const restore = useRestoreBackup();
  const del = useDeleteBackup();
  const rollback = useRollback();
  const { data: policy } = useBackupPolicy();
  const savePolicy = useSaveBackupPolicy();

  const [auto, setAuto] = useState(false);
  const [interval, setIntervalMin] = useState(360);
  const [retention, setRetention] = useState(10);
  useEffect(() => {
    if (policy) { setAuto(policy.auto_enabled); setIntervalMin(policy.interval_min); setRetention(policy.retention); }
  }, [policy]);

  const doBackup = async () => {
    try { await backup.mutateAsync({ id, note: "手动" }); message.success("备份完成"); refetch(); }
    catch (e) { message.error((e as Error).message); }
  };
  const doRollback = async (shard: string, count: number) => {
    try { await rollback.mutateAsync({ id, shard, count }); message.success(`已请求 ${shard} 回滚 ${count} 个快照`); }
    catch (e) { message.error((e as Error).message); }
  };

  const cols: ColumnsType<Backup> = [
    { title: "时间", dataIndex: "created_at", render: (t) => dayjs.unix(t).format("MM-DD HH:mm:ss") },
    { title: "类型", dataIndex: "trigger", render: (t) => <Tag>{t}</Tag> },
    { title: "大小", dataIndex: "size", render: fmtSize },
    { title: "备注", dataIndex: "note", render: (t) => t || "—" },
    {
      title: "操作", width: 280, render: (_, b) => (
        <Space wrap>
          <Tooltip title="下载备份文件">
            <Button size="small" icon={<DownloadOutlined />} href={downloadBackupUrl(b.id)} target="_blank">下载</Button>
          </Tooltip>
          <Popconfirm title="还原会先停服并覆盖当前存档(会自动预备份)。确认?" okButtonProps={{ danger: true }}
            onConfirm={async () => { await restore.mutateAsync({ backupId: b.id, restart: true }); message.success("已还原并重启"); }}>
            <Button size="small" icon={<RollbackOutlined />}>还原并重启</Button>
          </Popconfirm>
          <Popconfirm title="删除该备份文件?"
            onConfirm={async () => { await del.mutateAsync({ backupId: b.id, instanceId: id }); message.success("已删除"); }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Card size="small" title="存档与快照(游戏内回滚)">
        <Alert type="info" banner style={{ marginBottom: 12 }}
          message={`快照随每日保存滚动生成,最多保留 ${saves?.max_snapshots ?? instance.max_snapshots} 份(= 可回滚 ${(saves?.max_snapshots ?? 6) - 1} 次);回滚需服务器在运行。`} />
        <Row gutter={16}>
          {(saves?.shards ?? []).map((s) => (
            <Col key={s.shard} xs={24} lg={12}>
              <Card size="small" type="inner" title={s.shard}>
                <Descriptions size="small" column={1}>
                  <Descriptions.Item label="存档大小">{fmtSize(s.size)}</Descriptions.Item>
                  <Descriptions.Item label="会话数">{s.sessions.length}</Descriptions.Item>
                  <Descriptions.Item label="会话 ID">{s.sessions.map((x) => x.session_id).join(", ") || "—"}</Descriptions.Item>
                </Descriptions>
                <Space style={{ marginTop: 8 }}>
                  <Button size="small" icon={<RollbackOutlined />} onClick={() => doRollback(s.shard, 1)}>回滚 1</Button>
                  <Button size="small" icon={<RollbackOutlined />} onClick={() => doRollback(s.shard, 3)}>回滚 3</Button>
                </Space>
              </Card>
            </Col>
          ))}
          {(!saves || saves.shards.every((s) => !s.exists)) && <Col span={24}><span style={{ color: "#6e6e73" }}>暂无存档(尚未生成世界)</span></Col>}
        </Row>
      </Card>

      <Card size="small" title="文件级备份"
        extra={<Button type="primary" icon={<CloudUploadOutlined />} loading={backup.isPending} onClick={doBackup}>立即备份</Button>}>
        <Table rowKey="id" size="small" dataSource={backups} columns={cols} pagination={{ pageSize: 6 }}
          locale={{ emptyText: "暂无备份" }} />
      </Card>

      <Card size="small" title="自动备份策略(全局)">
        <Space wrap size="large">
          <span>启用自动备份 <Switch checked={auto} onChange={setAuto} /></span>
          <span>间隔(分钟)<InputNumber min={1} value={interval} onChange={(v) => setIntervalMin(v ?? 360)} /></span>
          <span>保留份数 <InputNumber min={1} value={retention} onChange={(v) => setRetention(v ?? 10)} /></span>
          <Button type="primary" loading={savePolicy.isPending}
            onClick={async () => { await savePolicy.mutateAsync({ auto_enabled: auto, interval_min: interval, retention }); message.success("策略已保存"); }}>
            保存策略
          </Button>
        </Space>
        <div style={{ color: "#646262", fontSize: 12, marginTop: 8 }}>
          自动备份仅对运行中的实例生效;每次备份后按保留份数滚动清理。
        </div>
      </Card>
    </Space>
  );
}
