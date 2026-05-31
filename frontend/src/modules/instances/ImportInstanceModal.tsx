import { InboxOutlined } from "@ant-design/icons";
import { Alert, Form, Input, Modal, Upload, message } from "antd";
import type { RcFile } from "antd/es/upload";
import { useState } from "react";
import { useImportInstance } from "../../api/hooks";

/** 从外界存档导入:上传一个 Cluster 压缩包,系统解析并续上其世界。 */
export function ImportInstanceModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [form] = Form.useForm();
  const [file, setFile] = useState<RcFile | null>(null);
  const imp = useImportInstance();

  const submit = async () => {
    if (!file) { message.warning("请先选择存档压缩包"); return; }
    const v = await form.validateFields();
    const fd = new FormData();
    fd.append("file", file);
    if (v.name) fd.append("name", v.name);
    if (v.token) fd.append("token", v.token);
    try {
      const view = await imp.mutateAsync(fd);
      message.success(`已导入:${view.instance.name}(端口已重新分配,可直接启动)`);
      form.resetFields(); setFile(null); onClose();
    } catch (e) { message.error((e as Error).message); }
  };

  return (
    <Modal title="从外界存档导入实例" open={open} onCancel={onClose} onOk={submit}
      confirmLoading={imp.isPending} okText="导入" destroyOnClose>
      <Alert type="info" banner style={{ marginBottom: 12 }}
        message="上传一个完整 Cluster 目录的压缩包(含 cluster.ini 与 Master/Caves 及其 save/)。系统会解析配置、重新分配端口并保留存档,启动即续原世界(不重新生成)。支持 .tar.gz/.tgz/.tar/.zip。" />
      <Upload.Dragger
        maxCount={1}
        beforeUpload={(f) => { setFile(f); return false; }}
        onRemove={() => setFile(null)}
        accept=".tar.gz,.tgz,.tar,.zip,.gz"
      >
        <p className="ant-upload-drag-icon"><InboxOutlined /></p>
        <p className="ant-upload-text">点击或拖拽存档压缩包到此处</p>
        <p className="ant-upload-hint">{file ? `已选择:${file.name}` : "尚未选择文件"}</p>
      </Upload.Dragger>
      <Form form={form} layout="vertical" style={{ marginTop: 16 }}>
        <Form.Item name="name" label="名称(可选,默认取存档内 cluster_name)"><Input placeholder="留空=沿用存档名称" /></Form.Item>
        <Form.Item name="token" label="Cluster Token(可选)"
          tooltip="若存档不含 token 且要作为在线服,可在此提供;否则将以离线方式导入,可在『配置』里再改">
          <Input.TextArea rows={2} placeholder="留空=用存档内 token 或离线导入" />
        </Form.Item>
      </Form>
    </Modal>
  );
}
