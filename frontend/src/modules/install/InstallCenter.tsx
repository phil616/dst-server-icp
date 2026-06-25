import { CloudDownloadOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Space, Table, Tooltip, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useInstall, useJobs } from "../../api/hooks";
import type { Job } from "../../api/types";
import { LogViewer } from "../../components/LogViewer";
import { StateTag } from "../../components/StateTag";
import { useLogStream } from "../../hooks/useLogStream";

/** 安装与更新模块:SteamCMD / 服务端本体 / Workshop MOD,均为后台作业,输出实时可见。 */
export function InstallCenter() {
  const install = useInstall();
  const { data: jobs = [] } = useJobs();
  const { lines, connected, clear } = useLogStream("/api/activity/ws");

  const trigger = async (kind: "steamcmd" | "server" | "mods") => {
    try {
      const job = await install.mutateAsync(kind);
      message.success(`作业 #${job.id} 已开始:${job.action}`);
    } catch (e) { message.error((e as Error).message); }
  };

  const dur = (j: Job) =>
    j.started_at && j.finished_at ? `${(j.finished_at - j.started_at).toFixed(1)}s` : "—";

  const cols: ColumnsType<Job> = [
    { title: "#", dataIndex: "id", width: 60 },
    { title: "作业", dataIndex: "action" },
    { title: "状态", dataIndex: "status", render: (s) => <StateTag state={s} /> },
    { title: "返回码", dataIndex: "returncode", render: (c) => (c == null ? "—" : c) },
    { title: "用时", render: (_, j) => dur(j) },
    { title: "开始", dataIndex: "started_at", render: (t) => (t ? dayjs.unix(t).format("HH:mm:ss") : "—") },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Card title="安装 / 更新">
        <Alert type="warning" banner style={{ marginBottom: 12 }}
          message="下载经『代理设置』里配置的代理(若启用)。运行态游戏进程不走代理。装有手动 MOD 时,服务端更新会自动避免误删(validate)。" />
        <Space wrap>
          <Tooltip title="下载并安装 SteamCMD">
            <Button icon={<CloudDownloadOutlined />} onClick={() => trigger("steamcmd")}>装/更 SteamCMD</Button>
          </Tooltip>
          <Tooltip title="app_update 343050,安装/更新 DST 服务端本体">
            <Button icon={<CloudDownloadOutlined />} onClick={() => trigger("server")}>装/更 服务端本体</Button>
          </Tooltip>
          <Tooltip title="-only_update_server_mods,更新所有声明的 Workshop MOD">
            <Button icon={<CloudDownloadOutlined />} onClick={() => trigger("mods")}>更新 Workshop MOD</Button>
          </Tooltip>
        </Space>
      </Card>

      <Card title="作业记录" size="small">
        <Table rowKey="id" size="small" dataSource={jobs} columns={cols} pagination={{ pageSize: 8 }}
          scroll={{ x: "max-content" }}
          locale={{ emptyText: "暂无作业" }} />
      </Card>

      <Card title="实时输出(活动流)" size="small">
        <LogViewer lines={lines} connected={connected} onClear={clear} height={300}
          title="安装/更新的逐行输出与后台事件" />
      </Card>
    </Space>
  );
}
