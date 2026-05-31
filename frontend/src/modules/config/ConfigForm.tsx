import { Alert, Button, Col, Form, Input, InputNumber, Row, Select, Space, Switch, message } from "antd";
import { useEffect } from "react";
import { useUpdateInstance } from "../../api/hooks";
import type { Instance } from "../../api/types";

/** 配置模块:房间/元信息/玩法/网络字段编辑(写回 cluster.ini,多数需重启生效)。 */
export function ConfigForm({ instance }: { instance: Instance }) {
  const [form] = Form.useForm();
  const update = useUpdateInstance();

  useEffect(() => { form.setFieldsValue(instance); }, [instance, form]);

  const submit = async () => {
    const v = await form.validateFields();
    try { await update.mutateAsync({ id: instance.id, patch: v }); message.success("已保存(重启对应 Shard 后生效)"); }
    catch (e) { message.error((e as Error).message); }
  };

  return (
    <Form form={form} layout="vertical" initialValues={instance} style={{ maxWidth: 880 }}>
      <Alert type="info" banner style={{ marginBottom: 16 }}
        message="多数配置改动需重启对应 Shard 才生效;whitelist_slots 应与白名单人数一致,且 ≤ 人数上限。" />
      <Row gutter={16}>
        <Col span={12}><Form.Item name="name" label="房间名称 (cluster_name)" rules={[{ required: true }]}><Input /></Form.Item></Col>
        <Col span={12}><Form.Item name="cluster_description" label="房间描述"><Input /></Form.Item></Col>
        <Col span={12}><Form.Item name="cluster_password" label="房间密码(空=无密码)"><Input.Password /></Form.Item></Col>
        <Col span={6}><Form.Item name="game_mode" label="游戏模式">
          <Select options={["survival", "endless", "wilderness"].map((v) => ({ value: v, label: v }))} /></Form.Item></Col>
        <Col span={6}><Form.Item name="cluster_intention" label="风格">
          <Select options={["cooperative", "competitive", "social", "madness"].map((v) => ({ value: v, label: v }))} /></Form.Item></Col>
        <Col span={6}><Form.Item name="max_players" label="人数上限"><InputNumber min={1} max={64} style={{ width: "100%" }} /></Form.Item></Col>
        <Col span={6}><Form.Item name="whitelist_slots" label="白名单保留位"><InputNumber min={0} max={64} style={{ width: "100%" }} /></Form.Item></Col>
        <Col span={6}><Form.Item name="max_snapshots" label="快照保留数"><InputNumber min={1} max={50} style={{ width: "100%" }} /></Form.Item></Col>
        <Col span={6}><Form.Item name="tick_rate" label="tick_rate"><InputNumber min={10} max={60} style={{ width: "100%" }} /></Form.Item></Col>
        <Col span={6}><Form.Item name="pvp" label="PVP" valuePropName="checked"><Switch /></Form.Item></Col>
        <Col span={6}><Form.Item name="pause_when_empty" label="无人时暂停" valuePropName="checked"><Switch /></Form.Item></Col>
        <Col span={6}><Form.Item name="vote_enabled" label="投票" valuePropName="checked"><Switch /></Form.Item></Col>
        <Col span={6}><Form.Item name="autosaver_enabled" label="每日自动保存" valuePropName="checked"><Switch /></Form.Item></Col>
        <Col span={6}><Form.Item name="lan_only_cluster" label="仅局域网" valuePropName="checked"><Switch /></Form.Item></Col>
        <Col span={6}><Form.Item name="online" label="在线服" valuePropName="checked"><Switch /></Form.Item></Col>
        <Col span={24}><Form.Item name="token" label="Cluster Token(在线服必填,此处为明文,可直接修改)"
          tooltip="在 DST 客户端控制台执行 TheNet:GenerateClusterToken() 获取;保存后写入 cluster_token.txt">
          <Input.TextArea rows={2} placeholder="pds-g^KU_..." /></Form.Item></Col>
      </Row>
      <Space>
        <Button type="primary" loading={update.isPending} onClick={submit}>保存配置</Button>
        <Button onClick={() => form.setFieldsValue(instance)}>重置</Button>
      </Space>
    </Form>
  );
}
