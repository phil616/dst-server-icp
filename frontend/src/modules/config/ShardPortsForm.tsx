import { Alert, Button, Card, Form, InputNumber, Space, Tag, message } from "antd";
import { useEffect } from "react";
import { useUpdateShardPorts } from "../../api/hooks";
import type { Shard } from "../../api/types";

const ACTIVE_STATES = new Set(["starting", "running", "ready", "stopping"]);

/** 自定义各 Shard(Master / Caves)的端口,写回对应 server.ini(重启该 Shard 后生效)。 */
export function ShardPortsForm({ instanceId, shards }: { instanceId: number; shards: Shard[] }) {
  const [form] = Form.useForm();
  const update = useUpdateShardPorts();
  const running = shards.some((s) => s.runtime && ACTIVE_STATES.has(s.runtime.state));

  useEffect(() => {
    const values: Record<string, number> = {};
    for (const s of shards) {
      values[`${s.shard_dir_name}__server_port`] = s.server_port;
      values[`${s.shard_dir_name}__master_server_port`] = s.master_server_port;
      values[`${s.shard_dir_name}__authentication_port`] = s.authentication_port;
    }
    form.setFieldsValue(values);
  }, [shards, form]);

  const save = async (shard: Shard) => {
    const v = await form.validateFields();
    const ports = {
      server_port: v[`${shard.shard_dir_name}__server_port`],
      master_server_port: v[`${shard.shard_dir_name}__master_server_port`],
      authentication_port: v[`${shard.shard_dir_name}__authentication_port`],
    };
    try {
      await update.mutateAsync({ id: instanceId, shard: shard.shard_dir_name, ports });
      message.success(`已保存 ${shard.shard_dir_name} 端口(重启该 Shard 后生效)`);
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  return (
    <Card size="small" title="Shard 端口设置">
      <Alert type="info" banner style={{ marginBottom: 16 }}
        message="自定义各 Shard(Master / Caves)的端口,保存后写回各自的 server.ini。玩家端口(server_port)默认 10998–11018 便于被局域网列表发现,但不强制,可设为任意 1024–65535 端口;改动需重启对应 Shard 生效。如果使用内网穿透请自行对应端口号" />
      {running && (
        <Alert type="warning" banner style={{ marginBottom: 16 }}
          message="该实例正在运行,修改端口不会立即生效,请保存后重启对应 Shard。" />
      )}
      <Form form={form} layout="vertical">
        {shards.map((s) => (
          <div key={s.id} style={{ marginBottom: 12 }}>
            <Space align="end" wrap>
              <div style={{ width: 80 }}>
                <Tag color={s.is_master ? "gold" : "default"}>{s.shard_dir_name}</Tag>
              </div>
              <Form.Item label="玩家端口 server_port" name={`${s.shard_dir_name}__server_port`}
                rules={[{ required: true, type: "number", min: 1024, max: 65535,
                  message: "1024–65535" }]} style={{ marginBottom: 0 }}>
                <InputNumber min={1024} max={65535} style={{ width: 190 }} />
              </Form.Item>
              <Form.Item label="master_server_port" name={`${s.shard_dir_name}__master_server_port`}
                rules={[{ required: true, type: "number", min: 1024, max: 65535,
                  message: "1024–65535" }]} style={{ marginBottom: 0 }}>
                <InputNumber min={1024} max={65535} style={{ width: 190 }} />
              </Form.Item>
              <Form.Item label="authentication_port" name={`${s.shard_dir_name}__authentication_port`}
                rules={[{ required: true, type: "number", min: 1024, max: 65535,
                  message: "1024–65535" }]} style={{ marginBottom: 0 }}>
                <InputNumber min={1024} max={65535} style={{ width: 190 }} />
              </Form.Item>
              <Button type="primary" loading={update.isPending} onClick={() => save(s)}>保存</Button>
            </Space>
          </div>
        ))}
      </Form>
    </Card>
  );
}
