import { CopyOutlined, ClearOutlined } from "@ant-design/icons";
import { Badge, Button, Space, Switch, Typography, message } from "antd";
import { useEffect, useRef, useState } from "react";

interface Props {
  lines: string[];
  connected: boolean;
  onClear?: () => void;
  height?: number;
  title?: string;
}

/** 通用日志查看器:自动滚动、复制、清屏、连接指示。 */
export function LogViewer({ lines, connected, onClear, height = 360, title }: Props) {
  const [autoscroll, setAutoscroll] = useState(true);
  const ref = useRef<HTMLPreElement>(null);

  useEffect(() => {
    if (autoscroll && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [lines, autoscroll]);

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(lines.join("\n"));
      message.success("已复制日志到剪贴板");
    } catch {
      const ta = document.createElement("textarea");
      ta.value = lines.join("\n");
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
      message.success("已复制日志(兼容模式)");
    }
  };

  return (
    <div>
      <Space style={{ marginBottom: 8, width: "100%", justifyContent: "space-between" }}>
        <Space>
          <Badge status={connected ? "success" : "error"} text={connected ? "已连接" : "未连接"} />
          {title && <Typography.Text type="secondary">{title}</Typography.Text>}
        </Space>
        <Space>
          <Switch checkedChildren="自动滚动" unCheckedChildren="自动滚动"
            checked={autoscroll} onChange={setAutoscroll} size="small" />
          <Button size="small" icon={<CopyOutlined />} onClick={copy}>复制</Button>
          {onClear && <Button size="small" icon={<ClearOutlined />} onClick={onClear}>清屏</Button>}
        </Space>
      </Space>
      <pre
        ref={ref}
        style={{
          height, overflow: "auto", margin: 0, padding: 12, borderRadius: 8,
          background: "#0a0d12", border: "1px solid #2a313c", color: "#cdd6e3",
          fontSize: 12.5, whiteSpace: "pre-wrap", wordBreak: "break-all",
          fontFamily: "ui-monospace, Menlo, Consolas, monospace",
        }}
      >
        {lines.join("\n") || "（暂无日志）"}
      </pre>
    </div>
  );
}
