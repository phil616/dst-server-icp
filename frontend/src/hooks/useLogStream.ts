import { useEffect, useRef, useState } from "react";
import { wsBase } from "../api/client";

/** 跟随一条 WS 日志流;自动重连,缓冲行数封顶。返回行数组与连接状态。 */
export function useLogStream(path: string | null, cap = 5000) {
  const [lines, setLines] = useState<string[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!path) return;
    setLines([]);
    let closed = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      const ws = new WebSocket(`${wsBase()}${path}`);
      wsRef.current = ws;
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (e) =>
        setLines((prev) => {
          const next = prev.length > cap ? prev.slice(prev.length - cap) : prev.slice();
          next.push(e.data as string);
          return next;
        });
    };
    connect();

    return () => {
      closed = true;
      clearTimeout(retry);
      wsRef.current?.close();
    };
  }, [path, cap]);

  return { lines, connected, clear: () => setLines([]) };
}
