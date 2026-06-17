import { Alert, Button, Form, Input, Space, message } from "antd";
import { useEffect } from "react";
import { useAiSettings, useSaveAiSettings } from "../../api/hooks";
import type { AiSettings } from "../../api/types";

export function SettingsPage() {
  const [form] = Form.useForm<AiSettings>();
  const { data } = useAiSettings();
  const save = useSaveAiSettings();

  useEffect(() => {
    if (data) form.setFieldsValue(data);
  }, [data, form]);

  const submit = async () => {
    const values = await form.validateFields();
    try {
      await save.mutateAsync(values);
      message.success("设置已保存");
    } catch (e) {
      message.error((e as Error).message);
    }
  };

  return (
    <Space direction="vertical" style={{ width: "100%", maxWidth: 760 }} size="middle">
      <Alert
        type="info"
        banner
        message="AI 翻译只用于 MOD 配置界面的显示文案,不会修改 MOD 的配置键和值。APIKey、Base URL 和模型名称会以明文保存。"
      />
      <Form
        form={form}
        layout="vertical"
        initialValues={{ api_base: "https://api.openai.com/v1", api_key: "", model: "" }}
      >
        <Form.Item
          name="api_base"
          label="OpenAI-compatible Base URL"
          rules={[{ required: true, message: "请输入 API Base URL" }]}
        >
          <Input placeholder="https://api.openai.com/v1" />
        </Form.Item>
        <Form.Item name="api_key" label="APIKey" rules={[{ required: true, message: "请输入 APIKey" }]}>
          <Input placeholder="sk-..." />
        </Form.Item>
        <Form.Item name="model" label="模型名称" rules={[{ required: true, message: "请输入模型名称" }]}>
          <Input placeholder="例如 gpt-4o-mini / deepseek-chat / qwen-plus" />
        </Form.Item>
        <Button type="primary" loading={save.isPending} onClick={submit}>保存设置</Button>
      </Form>
    </Space>
  );
}
