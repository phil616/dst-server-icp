import {
  AppstoreOutlined, CloudDownloadOutlined, DashboardOutlined,
  ProfileOutlined, ApiOutlined, FireOutlined,
} from "@ant-design/icons";
import { Badge, Button, Layout, Menu } from "antd";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useProxy } from "../api/hooks";
import { ActivityDrawer } from "./ActivityDrawer";

const { Header, Sider, Content } = Layout;

const ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: <Link to="/">运行总览</Link> },
  { key: "/instances", icon: <AppstoreOutlined />, label: <Link to="/instances">实例管理</Link> },
  { key: "/install", icon: <CloudDownloadOutlined />, label: <Link to="/install">安装与更新</Link> },
  { key: "/proxy", icon: <ApiOutlined />, label: <Link to="/proxy">代理设置</Link> },
];

export function AppLayout({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const [activityOpen, setActivityOpen] = useState(false);
  const { data: proxy } = useProxy();
  // 选中项:取与当前路径最匹配的菜单 key
  const selected =
    ITEMS.map((i) => i.key).filter((k) => k === "/" ? loc.pathname === "/" : loc.pathname.startsWith(k))
      .sort((a, b) => b.length - a.length)[0] ?? "/";

  return (
    <Layout style={{ minHeight: "100vh" }}>
      <Sider theme="dark" breakpoint="lg" collapsedWidth={0}>
        <div style={{ height: 56, display: "flex", alignItems: "center", gap: 8, padding: "0 20px",
          color: "#e8b339", fontSize: 18, fontWeight: 700 }}>
          <FireOutlined /> DST Serverd
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[selected]} items={ITEMS} />
      </Sider>
      <Layout>
        <Header style={{ display: "flex", alignItems: "center", gap: 16, padding: "0 20px",
          background: "#161b22", borderBottom: "1px solid #2a313c" }}>
          <ProfileOutlined />
          <span style={{ color: "#9aa7b8" }}>饥荒联机版服务器管理</span>
          <span style={{ marginLeft: "auto" }}>
            <Badge
              status={proxy?.active ? "processing" : "default"}
              text={<span style={{ color: "#8b97a8" }}>
                代理：{proxy?.active ? `${proxy.scheme}://${proxy.host}:${proxy.port}` : "关闭"}
              </span>}
            />
          </span>
          <Button type="primary" ghost onClick={() => setActivityOpen(true)}>系统日志</Button>
        </Header>
        <Content style={{ padding: 20, overflow: "auto" }}>{children}</Content>
      </Layout>
      <ActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} />
    </Layout>
  );
}
