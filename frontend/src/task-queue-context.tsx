import { createContext, useCallback, useContext, useMemo, useState } from "react";
import { TaskQueueDrawer } from "./components/TaskQueueDrawer";

interface TaskQueueCtx {
  open: () => void;
  close: () => void;
  isOpen: boolean;
}

const Ctx = createContext<TaskQueueCtx | null>(null);

/** 全局任务队列:提供 open()/close(),并渲染唯一的「任务队列」抽屉。
 *  这样头部按钮、MOD 管理页等深层组件都能唤起同一个抽屉(如点 MOD 更新后自动弹出)。 */
export function TaskQueueProvider({ children }: { children: React.ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);
  const close = useCallback(() => setIsOpen(false), []);
  const value = useMemo(() => ({ open, close, isOpen }), [open, close, isOpen]);
  return (
    <Ctx.Provider value={value}>
      {children}
      <TaskQueueDrawer open={isOpen} onClose={close} />
    </Ctx.Provider>
  );
}

export function useTaskQueue(): TaskQueueCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useTaskQueue 必须在 TaskQueueProvider 内使用");
  return c;
}
