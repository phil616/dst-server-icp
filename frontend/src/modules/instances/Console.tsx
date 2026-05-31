import { SendOutlined } from "@ant-design/icons";
import { Button, Input, Segmented, Space, message } from "antd";
import { useMemo, useState } from "react";
import { useSendCommand } from "../../api/hooks";
import type { Shard } from "../../api/types";
import { LogViewer } from "../../components/LogViewer";
import { useLogStream } from "../../hooks/useLogStream";

/** 控制台模块:选 Shard → 实时日志(WS)+ 注入控制台命令。 */
export function Console({ instanceId, cluster, shards }: { instanceId: number; cluster: string; shards: Shard[] }) {
  const [shard, setShard] = useState(shards[0]?.shard_dir_name ?? "Master");
  const [cmd, setCmd] = useState("");
  const send = useSendCommand();
  const path = useMemo(
    () => `/api/instances/${encodeURIComponent(cluster)}/shards/${encodeURIComponent(shard)}/logs/ws`,
    [cluster, shard],
  );
  const { lines, connected, clear } = useLogStream(path);

  const submit = async () => {
    if (!cmd.trim()) return;
    try { await send.mutateAsync({ id: instanceId, shard, command: cmd }); setCmd(""); message.success("命令已发送"); }
    catch (e) { message.error((e as Error).message); }
  };

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Space wrap>
        <Segmented value={shard} onChange={(v) => setShard(v as string)}
          options={shards.map((s) => s.shard_dir_name)} />
      </Space>
      <Space.Compact style={{ width: "100%" }}>
        <Input value={cmd} onChange={(e) => setCmd(e.target.value)} onPressEnter={submit}
          placeholder='控制台命令,如 c_listplayers() / c_announce("msg") / c_save()' />
        <Button type="primary" icon={<SendOutlined />} onClick={submit}>发送</Button>
      </Space.Compact>
      <LogViewer lines={lines} connected={connected} onClear={clear} height={420} title={`${cluster}/${shard} 实时日志`} />
    </Space>
  );
}
