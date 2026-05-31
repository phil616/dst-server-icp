import { Drawer } from "antd";
import { useLogStream } from "../hooks/useLogStream";
import { LogViewer } from "./LogViewer";

/** 全局「系统日志」抽屉:实时跟随活动流(后台在做什么 + 安装/更新输出)。 */
export function ActivityDrawer({ open, onClose }: { open: boolean; onClose: () => void }) {
  // 仅在打开时建立 WS 连接
  const { lines, connected, clear } = useLogStream(open ? "/api/activity/ws" : null);
  return (
    <Drawer
      title="🖥 系统日志 · 实时活动流"
      placement="bottom"
      height={460}
      open={open}
      onClose={onClose}
      styles={{ body: { paddingTop: 8 } }}
    >
      <LogViewer
        lines={lines}
        connected={connected}
        onClear={clear}
        height={360}
        title="后台编排事件、Shard 状态流转、安装/更新输出"
      />
    </Drawer>
  );
}
