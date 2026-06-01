import { DeleteOutlined, PlusOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Col, Input, List, Row, Space, Tag, message } from "antd";
import { useState } from "react";
import { useAddAccess, useRemoveAccess } from "../../api/hooks";
import type { AccessEntry, AccessKind, Instance } from "../../api/types";

const KINDS: { kind: AccessKind; title: string; color: string; desc: string }[] = [
  { kind: "admin", title: "管理员 (adminlist)", color: "gold", desc: "可踢人/封禁/执行 Lua,谨慎授予" },
  { kind: "whitelist", title: "白名单 (whitelist)", color: "green", desc: "保留座位,随时可进;条目数应 = whitelist_slots" },
  { kind: "blocklist", title: "黑名单 (blocklist)", color: "red", desc: "禁止进入;游戏内封禁也会自动写入" },
];

function ListCard({ instanceId, kind, title, color, desc, entries, slots }: {
  instanceId: number; kind: AccessKind; title: string; color: string; desc: string;
  entries: AccessEntry[]; slots?: number;
}) {
  const [val, setVal] = useState("");
  const add = useAddAccess();
  const remove = useRemoveAccess();

  const onAdd = async () => {
    if (!val.trim()) return;
    try { await add.mutateAsync({ id: instanceId, kind, klei_id: val.trim() }); setVal(""); message.success("已添加(重启后生效)"); }
    catch (e) { message.error((e as Error).message); }
  };

  const slotWarn = kind === "whitelist" && slots != null && slots !== entries.length;

  return (
    <Card size="small" title={<span><Tag color={color}>{title}</Tag></span>}>
      <div style={{ color: "#646262", fontSize: 12, marginBottom: 8 }}>{desc}</div>
      {slotWarn && <Alert type="warning" banner style={{ marginBottom: 8 }}
        message={`白名单条目 ${entries.length} 个,但 whitelist_slots=${slots};建议在『配置』里改为一致。`} />}
      <Space.Compact style={{ display: "flex", marginBottom: 8 }}>
        <Input value={val} onChange={(e) => setVal(e.target.value)} onPressEnter={onAdd}
          placeholder="KU_xxxx(在线)/ OU_xxxx(离线)" />
        <Button type="primary" icon={<PlusOutlined />} onClick={onAdd}>添加</Button>
      </Space.Compact>
      <List size="small" dataSource={entries} locale={{ emptyText: "（空)" }}
        renderItem={(e) => (
          <List.Item actions={[
            <Button key="d" size="small" danger icon={<DeleteOutlined />}
              onClick={async () => { await remove.mutateAsync({ id: instanceId, kind, kleiId: e.klei_id }); message.success("已移除"); }} />,
          ]}>
            <code>{e.klei_id}</code>{e.note && <span style={{ color: "#6e6e73" }}> · {e.note}</span>}
          </List.Item>
        )} />
    </Card>
  );
}

/** 访问控制模块:管理员 / 白名单 / 黑名单(写回三个 txt,重启后生效)。 */
export function AccessControl({ instance, access }: { instance: Instance; access: AccessEntry[] }) {
  return (
    <Row gutter={16}>
      {KINDS.map((k) => (
        <Col key={k.kind} xs={24} lg={8}>
          <ListCard instanceId={instance.id} {...k}
            entries={access.filter((a) => a.kind === k.kind)}
            slots={k.kind === "whitelist" ? instance.whitelist_slots : undefined} />
        </Col>
      ))}
    </Row>
  );
}
