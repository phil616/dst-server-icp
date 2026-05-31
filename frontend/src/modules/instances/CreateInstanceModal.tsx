import { Form, Input, InputNumber, Modal, Select, Switch, message } from "antd";
import { useCreateInstance } from "../../api/hooks";
import type { CreateInstancePayload } from "../../api/types";

export function CreateInstanceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm();
  const create = useCreateInstance();
  const online = Form.useWatch("online", form);

  const submit = async () => {
    const v = await form.validateFields();
    try {
      await create.mutateAsync(v as CreateInstancePayload);
      message.success("实例已创建");
      form.resetFields();
      onClose();
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  return (
    <Modal title="新建实例(Cluster)" open={open} onCancel={onClose} onOk={submit}
      confirmLoading={create.isPending} okText="创建" destroyOnClose>
      <Form form={form} layout="vertical" initialValues={{
        online: true, caves: true, pvp: false, game_mode: "survival",
        max_players: 6, cluster_intention: "cooperative", token: "",
      }}>
        <Form.Item name="name" label="服务器名称" rules={[{ required: true, message: "请输入名称" }]}>
          <Input placeholder="My DST Server" />
        </Form.Item>
        <Form.Item name="game_mode" label="游戏模式">
          <Select options={[
            { value: "survival", label: "生存 survival" },
            { value: "endless", label: "无尽 endless" },
            { value: "wilderness", label: "荒野 wilderness" },
          ]} />
        </Form.Item>
        <Form.Item name="cluster_intention" label="风格">
          <Select options={["cooperative", "competitive", "social", "madness"].map((v) => ({ value: v, label: v }))} />
        </Form.Item>
        <Form.Item name="max_players" label="人数上限"><InputNumber min={1} max={64} /></Form.Item>
        <Form.Item name="caves" label="包含洞穴(双 Shard)" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name="pvp" label="PVP" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name="online" label="在线服(需 Klei Token)" valuePropName="checked"><Switch /></Form.Item>
        <Form.Item name="token" label="Cluster Token"
          rules={online ? [{ required: true, message: "在线服必须填写 Token" }] : []}
          tooltip="在 DST 客户端控制台执行 TheNet:GenerateClusterToken() 获取">
          <Input.TextArea rows={2} placeholder="pds-g^KU_..." />
        </Form.Item>
      </Form>
    </Modal>
  );
}
