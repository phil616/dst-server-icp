import { CloseCircleOutlined, LoadingOutlined } from "@ant-design/icons";
import { Badge, Button, Drawer, Empty, Popconfirm, Space, Table, Tag, Tooltip, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useCancelJob, useJobs } from "../api/hooks";
import type { Job } from "../api/types";

const STATUS: Record<Job["status"], { color: string; text: string }> = {
  queued: { color: "default", text: "排队中" },
  running: { color: "processing", text: "执行中" },
  success: { color: "success", text: "成功" },
  failed: { color: "error", text: "失败" },
  canceled: { color: "warning", text: "已取消" },
};

/** 作业用时:已结束算 started→finished;执行中算 started→现在;排队中显示「等待」。 */
function duration(j: Job): string {
  if (j.status === "queued") return "等待执行";
  if (j.started_at == null) return "—";
  const end = j.finished_at ?? Date.now() / 1000;
  const s = Math.max(0, Math.round(end - j.started_at));
  return s >= 60 ? `${Math.floor(s / 60)}分${s % 60}秒` : `${s}秒`;
}

/** 全局「任务队列」抽屉:可视化后台作业(安装/更新/MOD 下载等),并可删除排队中未执行的作业。 */
export function TaskQueueDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  const { data: jobs = [], isLoading } = useJobs();
  const cancel = useCancelJob();

  const active = jobs.filter((j) => j.status === "queued" || j.status === "running").length;

  const doCancel = async (job: Job) => {
    const running = job.status === "running";
    try {
      await cancel.mutateAsync(job.id);
      message.success(running ? `已强制中断作业 #${job.id}` : `已删除排队作业 #${job.id}`);
    } catch (e) { message.error((e as Error).message); }
  };

  const columns: ColumnsType<Job> = [
    { title: "#", dataIndex: "id", width: 56, render: (id: number) => <code>#{id}</code> },
    {
      title: "作业", dataIndex: "action",
      render: (a: string, j) => (
        <Space size={6}>
          {j.status === "running" && <LoadingOutlined />}
          <span>{a}</span>
        </Space>
      ),
    },
    {
      title: "状态", dataIndex: "status", width: 96,
      render: (s: Job["status"], j) => (
        <Tooltip title={j.status === "failed" ? j.error : undefined}>
          <Tag color={STATUS[s].color}>{STATUS[s].text}</Tag>
        </Tooltip>
      ),
    },
    {
      title: "提交时间", dataIndex: "created_at", width: 96,
      render: (t: number) => dayjs.unix(t).format("HH:mm:ss"),
    },
    { title: "用时", width: 90, render: (_, j) => duration(j) },
    {
      title: "操作", width: 88,
      render: (_, j) => {
        if (j.status === "queued") {
          return (
            <Popconfirm title="删除该排队作业?(尚未执行)" okText="删除" cancelText="取消"
              onConfirm={() => doCancel(j)}>
              <Tooltip title="删除排队中、尚未执行的作业">
                <Button size="small" danger icon={<CloseCircleOutlined />}>删除</Button>
              </Tooltip>
            </Popconfirm>
          );
        }
        if (j.status === "running") {
          return (
            <Popconfirm title="强制中断正在执行的任务?将立即杀掉下载进程" okText="强制中断" cancelText="取消"
              onConfirm={() => doCancel(j)}>
              <Tooltip title="强制终止正在执行的下载/更新(SIGKILL),立即脱困">
                <Button size="small" danger icon={<CloseCircleOutlined />}>中断</Button>
              </Tooltip>
            </Popconfirm>
          );
        }
        return <span style={{ color: "#9aa0a6" }}>—</span>;
      },
    },
  ];

  return (
    <Drawer
      title={<Space>📋 任务队列<Badge count={active} showZero={false} /></Space>}
      placement="right" width={620} open={open} onClose={onClose}
      styles={{ body: { paddingTop: 8 } }}
    >
      <div style={{ color: "#6e6e73", fontSize: 12, marginBottom: 8 }}>
        作业串行执行(同一时刻只跑一个)。排队中的作业可删除;执行中的可强制中断(立即杀掉下载进程)。实时输出见「系统日志」。
      </div>
      <Table<Job>
        rowKey="id" size="small" columns={columns} dataSource={jobs} loading={isLoading}
        pagination={jobs.length > 12 ? { pageSize: 12 } : false}
        locale={{ emptyText: <Empty description="暂无任务" /> }}
      />
    </Drawer>
  );
}
