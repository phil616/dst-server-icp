import { Alert, Button, Card, Form, Input, InputNumber, Select, Space, Switch, message } from "antd";
import { useEffect } from "react";
import { useProxy, useSaveProxy } from "../../api/hooks";

/** 代理设置模块:仅作用于 SteamCMD/本体/MOD 下载子进程(见 DESIGN.md 2.9)。 */
export function ProxySettings() {
  const { data: proxy } = useProxy();
  const save = useSaveProxy();
  const [form] = Form.useForm();

  useEffect(() => {
    if (proxy) form.setFieldsValue({ ...proxy, password: "" });
  }, [proxy, form]);

  const submit = async () => {
    const v = await form.validateFields();
    try { await save.mutateAsync(v); message.success("代理配置已保存"); }
    catch (e) { message.error((e as Error).message); }
  };

  return (
    <Card title="下载代理设置" style={{ maxWidth: 640 }}>
      <Alert type="info" banner style={{ marginBottom: 16 }}
        message="代理只用于下载/更新(SteamCMD、服务端本体、MOD)。运行态游戏流量(玩家连接、Klei 中继、Shard 间通信)一律直连。" />
      <Form form={form} layout="vertical">
        <Form.Item name="enabled" label="启用代理" valuePropName="checked"><Switch /></Form.Item>
        <Space size="large" wrap>
          <Form.Item name="mode" label="模式" tooltip="env=注入环境变量;force=用 proxychains 强制路由(需宿主机装 proxychains-ng)">
            <Select style={{ width: 160 }} options={[
              { value: "env", label: "env(环境变量)" },
              { value: "force", label: "force(proxychains)" },
              { value: "off", label: "off(关闭)" },
            ]} />
          </Form.Item>
          <Form.Item name="scheme" label="协议">
            <Select style={{ width: 120 }} options={["http", "https", "socks5"].map((v) => ({ value: v, label: v }))} />
          </Form.Item>
        </Space>
        <Space size="large" wrap>
          <Form.Item name="host" label="主机"><Input style={{ width: 220 }} placeholder="127.0.0.1" /></Form.Item>
          <Form.Item name="port" label="端口"><InputNumber min={0} max={65535} placeholder="7890" /></Form.Item>
        </Space>
        <Space size="large" wrap>
          <Form.Item name="username" label="用户名(可选)"><Input style={{ width: 220 }} /></Form.Item>
          <Form.Item name="password" label="密码(留空=不修改)"><Input.Password style={{ width: 220 }} /></Form.Item>
        </Space>
        <Form.Item name="no_proxy" label="直连白名单(no_proxy)"><Input placeholder="127.0.0.1,localhost" /></Form.Item>
        <Button type="primary" loading={save.isPending} onClick={submit}>保存</Button>
      </Form>
    </Card>
  );
}
