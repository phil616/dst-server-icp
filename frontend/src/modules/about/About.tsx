import { GithubOutlined, InfoCircleOutlined, UserOutlined } from "@ant-design/icons";
import { Card, Descriptions, Space } from "antd";
import { useHealth } from "../../api/hooks";
import { MONO } from "../../theme";
import { useThemeMode } from "../../theme-context";

export function About() {
  const { data: health } = useHealth();
  const { colors: COLORS } = useThemeMode();

  return (
    <Space direction="vertical" size={20} style={{ width: "100%", maxWidth: 600 }}>
      <Card>
        <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 20 }}>
          <InfoCircleOutlined style={{ fontSize: 28, color: COLORS.ink }} />
          <span style={{ fontSize: 18, fontWeight: 700, color: COLORS.ink }}>
            饥荒服务器控制面板
          </span>
        </div>
        <p style={{ color: COLORS.body, lineHeight: 1.7, margin: 0 }}>
          Don't Starve Together 专用服务器管理后端。单机、无 Docker，Python 后端直接托管
          每个 Shard 进程，重启后自动重新接管已有 Shard，不打断玩家。
        </p>
      </Card>

      <Card title="作者">
        <Descriptions column={1} size="small" labelStyle={{ fontFamily: MONO, color: COLORS.mute }}>
          <Descriptions.Item label={<span><UserOutlined /> 作者</span>}>
            <span style={{ fontFamily: MONO, fontWeight: 700, color: COLORS.ink }}>phil616</span>
          </Descriptions.Item>
          <Descriptions.Item label={<span><GithubOutlined /> GitHub</span>}>
            <a href="https://github.com/phil616/dst-server-icp" target="_blank" rel="noreferrer"
              style={{ fontFamily: MONO, color: COLORS.ink }}>github.com/phil616/dst-server-icp</a>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="版本信息">
        <Descriptions column={1} size="small" labelStyle={{ fontFamily: MONO, color: COLORS.mute }}>
          <Descriptions.Item label="后端版本">
            <span style={{ fontFamily: MONO }}>{health?.version ?? "—"}</span>
          </Descriptions.Item>
          <Descriptions.Item label="Python 版本">
            <span style={{ fontFamily: MONO }}>{health?.python ?? "—"}</span>
          </Descriptions.Item>
          <Descriptions.Item label="运行平台">
            <span style={{ fontFamily: MONO }}>{health?.platform ?? "—"}</span>
          </Descriptions.Item>
          <Descriptions.Item label="前端框架">
            <span style={{ fontFamily: MONO }}>React + TypeScript + Ant Design</span>
          </Descriptions.Item>
        </Descriptions>
      </Card>

      <Card title="技术栈">
        <Descriptions column={1} size="small" labelStyle={{ fontFamily: MONO, color: COLORS.mute }}>
          <Descriptions.Item label="后端">FastAPI + uvicorn + psutil</Descriptions.Item>
          <Descriptions.Item label="前端">React 18 + TypeScript + Vite</Descriptions.Item>
          <Descriptions.Item label="UI">Ant Design 5</Descriptions.Item>
          <Descriptions.Item label="数据请求">TanStack Query + axios</Descriptions.Item>
          <Descriptions.Item label="持久化">SQLite</Descriptions.Item>
          <Descriptions.Item label="进程托管">subprocess + FIFO + PID 文件</Descriptions.Item>
        </Descriptions>
      </Card>
    </Space>
  );
}
