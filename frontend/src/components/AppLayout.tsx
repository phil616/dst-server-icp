import {
  AppstoreOutlined, CloudDownloadOutlined, DashboardOutlined,
  InfoCircleOutlined, ProfileOutlined, ApiOutlined, FireOutlined,
  BulbOutlined, BulbFilled,
} from "@ant-design/icons";
import { Badge, Breadcrumb, Button, Layout, Menu, Tooltip } from "antd";
import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { useProxy } from "../api/hooks";
import { useThemeMode } from "../theme-context";
import { ActivityDrawer } from "./ActivityDrawer";

const { Header, Sider, Content, Footer } = Layout;

const ITEMS = [
  { key: "/", icon: <DashboardOutlined />, label: <Link to="/">运行总览</Link> },
  { key: "/instances", icon: <AppstoreOutlined />, label: <Link to="/instances">实例管理</Link> },
  { key: "/install", icon: <CloudDownloadOutlined />, label: <Link to="/install">安装与更新</Link> },
  { key: "/proxy", icon: <ApiOutlined />, label: <Link to="/proxy">代理设置</Link> },
  { key: "/about", icon: <InfoCircleOutlined />, label: <Link to="/about">关于</Link> },
];

// 路径 → 面包屑中文名
const CRUMB_LABELS: Record<string, string> = {
  "/": "运行总览",
  "/instances": "实例管理",
  "/install": "安装与更新",
  "/proxy": "代理设置",
  "/about": "关于",
};

/** 由当前路径构建面包屑项;实例详情等动态段落给出友好名称。 */
function buildCrumbs(pathname: string) {
  const items: { title: React.ReactNode }[] = [
    { title: <Link to="/">运行总览</Link> },
  ];
  if (pathname === "/") return items;

  const segs = pathname.split("/").filter(Boolean);
  let acc = "";
  segs.forEach((seg, idx) => {
    acc += `/${seg}`;
    const isLast = idx === segs.length - 1;
    let label = CRUMB_LABELS[acc];
    if (!label) label = acc.startsWith("/instances/") ? "实例详情" : decodeURIComponent(seg);
    items.push({
      title: isLast || !CRUMB_LABELS[acc] ? <span>{label}</span> : <Link to={acc}>{label}</Link>,
    });
  });
  return items;
}

export function AppLayout({ children }: { children: React.ReactNode }) {
  const loc = useLocation();
  const [activityOpen, setActivityOpen] = useState(false);
  const { data: proxy } = useProxy();
  const { mode, colors, toggle } = useThemeMode();
  // 选中项:取与当前路径最匹配的菜单 key
  const selected =
    ITEMS.map((i) => i.key).filter((k) => k === "/" ? loc.pathname === "/" : loc.pathname.startsWith(k))
      .sort((a, b) => b.length - a.length)[0] ?? "/";

  return (
    <Layout style={{ minHeight: "100vh", background: colors.canvas }}>
      <Sider theme={mode} breakpoint="lg" collapsedWidth={0}
        style={{ background: colors.canvas, borderInlineEnd: `1px solid ${colors.hairline}` }}>
        <div style={{ height: 56, display: "flex", alignItems: "center", gap: 8, padding: "0 20px",
          color: colors.ink, fontSize: 16, fontWeight: 700,
          borderBottom: `1px solid ${colors.hairline}` }}>
          <FireOutlined /> 控制面板
        </div>
        <Menu theme={mode} mode="inline" selectedKeys={[selected]} items={ITEMS}
          style={{ background: "transparent", borderInlineEnd: "none" }} />
      </Sider>
      <Layout style={{ background: colors.canvas }}>
        <Header style={{ display: "flex", alignItems: "center", gap: 16, padding: "0 20px",
          background: colors.canvas, borderBottom: `1px solid ${colors.hairline}` }}>
          <ProfileOutlined style={{ color: colors.ink }} />
          <span style={{ color: colors.mute }}>饥荒联机版服务器管理</span>
          <span style={{ marginLeft: "auto" }}>
            <Badge
              status={proxy?.active ? "processing" : "default"}
              text={<span style={{ color: colors.mute }}>
                代理：{proxy?.active ? `${proxy.scheme}://${proxy.host}:${proxy.port}` : "关闭"}
              </span>}
            />
          </span>
          <Tooltip title={mode === "dark" ? "切换为亮色" : "切换为暗色"}>
            <Button type="text" aria-label="切换主题"
              icon={mode === "dark" ? <BulbFilled /> : <BulbOutlined />}
              onClick={toggle} style={{ color: colors.ink }} />
          </Tooltip>
          <Button type="primary" ghost onClick={() => setActivityOpen(true)}>系统日志</Button>
        </Header>
        <div style={{ padding: "12px 20px", borderBottom: `1px solid ${colors.hairline}`,
          background: colors.canvas }}>
          <Breadcrumb items={buildCrumbs(loc.pathname)} />
        </div>
        <Content style={{ padding: 20, overflow: "auto", background: colors.canvas }}>{children}</Content>
        <Footer style={{ textAlign: "center", background: colors.canvas, color: colors.mute,
          fontSize: 13, padding: "16px 20px", borderTop: `1px solid ${colors.hairline}` }}>
          饥荒服务器控制面板 ·{" "}
          <a href="https://github.com/phil616/dst-server-icp" target="_blank" rel="noreferrer"
            style={{ color: colors.ink }}>phil616/dst-server-icp</a>
          {" "}· © 2026
        </Footer>
      </Layout>
      <ActivityDrawer open={activityOpen} onClose={() => setActivityOpen(false)} />
    </Layout>
  );
}
