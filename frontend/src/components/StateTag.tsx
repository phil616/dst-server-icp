import { Tag } from "antd";
import type { ShardState } from "../api/types";

const MAP: Record<string, { color: string; text: string }> = {
  ready: { color: "success", text: "就绪" },
  running: { color: "processing", text: "运行中" },
  starting: { color: "gold", text: "启动中" },
  stopping: { color: "gold", text: "停止中" },
  stopped: { color: "default", text: "已停止" },
  crashed: { color: "error", text: "已崩溃" },
  created: { color: "default", text: "未启动" },
  queued: { color: "default", text: "排队中" },
  success: { color: "success", text: "成功" },
  failed: { color: "error", text: "失败" },
};

export function StateTag({ state }: { state: ShardState | string }) {
  const m = MAP[state] ?? { color: "default", text: state };
  return <Tag color={m.color}>{m.text}</Tag>;
}
