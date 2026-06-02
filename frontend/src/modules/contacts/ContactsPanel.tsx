import { CopyOutlined, DeleteOutlined, TeamOutlined } from "@ant-design/icons";
import {
  Alert, Button, Card, Empty, Input, Popconfirm, Space, Table, Tag, Tooltip, Typography, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useState } from "react";
import { useContacts, useDeleteContact, useUpdateContact } from "../../api/hooks";
import type { Contact } from "../../api/types";

/** 复制文本到剪贴板;clipboard API 不可用时退回 execCommand。 */
async function copy(text: string): Promise<boolean> {
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(text);
      return true;
    }
  } catch { /* 退回兜底 */ }
  try {
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.style.position = "fixed";
    ta.style.opacity = "0";
    document.body.appendChild(ta);
    ta.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(ta);
    return ok;
  } catch {
    return false;
  }
}

/** 行内可编辑的备注单元格。 */
function NoteCell({ contact }: { contact: Contact }) {
  const update = useUpdateContact();
  const [val, setVal] = useState(contact.note);
  const dirty = val !== contact.note;
  const save = async () => {
    if (!dirty) return;
    try { await update.mutateAsync({ kleiId: contact.klei_id, note: val }); message.success("备注已保存"); }
    catch (e) { message.error((e as Error).message); }
  };
  return (
    <Input
      size="small" value={val} placeholder="加个备注（如：老王 / 公会成员）"
      onChange={(e) => setVal(e.target.value)} onBlur={save} onPressEnter={save}
      suffix={dirty ? <Typography.Text type="warning" style={{ fontSize: 11 }}>未保存</Typography.Text> : null}
    />
  );
}

/** 本地通讯录:只要有玩家加入过游戏,系统就自动记下其 昵称↔Klei ID。可备注、复制、删除。 */
export function ContactsPanel() {
  const { data: contacts = [], isLoading } = useContacts();
  const del = useDeleteContact();
  const [q, setQ] = useState("");

  const kw = q.trim().toLowerCase();
  const rows = kw
    ? contacts.filter((c) =>
        c.name.toLowerCase().includes(kw) ||
        c.klei_id.toLowerCase().includes(kw) ||
        c.note.toLowerCase().includes(kw))
    : contacts;

  const doCopy = async (text: string, label: string) => {
    (await copy(text)) ? message.success(`已复制${label}`) : message.error("复制失败，请手动选择");
  };

  const columns: ColumnsType<Contact> = [
    {
      title: "玩家", dataIndex: "name", width: "26%",
      render: (_, c) => (
        <Space direction="vertical" size={0}>
          <span style={{ fontWeight: 600 }}>{c.name || "（未知昵称)"}</span>
          {c.seen_count > 0 && <Tag color="blue" style={{ marginInlineEnd: 0 }}>加入 {c.seen_count} 次</Tag>}
        </Space>
      ),
    },
    {
      title: "Klei ID", dataIndex: "klei_id",
      render: (_, c) => (
        <Space>
          <code>{c.klei_id}</code>
          <Tooltip title="复制 Klei ID">
            <Button size="small" type="text" icon={<CopyOutlined />}
              onClick={() => doCopy(c.klei_id, " ID")} />
          </Tooltip>
        </Space>
      ),
    },
    { title: "备注", dataIndex: "note", width: "24%", render: (_, c) => <NoteCell contact={c} /> },
    {
      title: "最近加入", dataIndex: "last_seen", width: 160,
      render: (t: number) => (t ? dayjs.unix(t).format("YYYY-MM-DD HH:mm") : "—"),
    },
    {
      title: "操作", width: 150,
      render: (_, c) => (
        <Space>
          <Tooltip title="复制 “昵称 ID” 整条">
            <Button size="small" icon={<CopyOutlined />}
              onClick={() => doCopy(`${c.name} ${c.klei_id}`.trim(), "该好友")}>复制</Button>
          </Tooltip>
          <Popconfirm title="从通讯录删除该玩家？" okText="删除" cancelText="取消"
            onConfirm={async () => {
              try { await del.mutateAsync(c.klei_id); message.success("已删除"); }
              catch (e) { message.error((e as Error).message); }
            }}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title={<Space><TeamOutlined />本地通讯录</Space>}
      extra={
        <Input.Search allowClear placeholder="搜索昵称 / ID / 备注" style={{ width: 240 }}
          value={q} onChange={(e) => setQ(e.target.value)} />
      }
    >
      <Alert type="info" banner style={{ marginBottom: 16 }}
        message="只要有玩家加入到游戏，系统就会自动把其昵称与 Klei ID 记到这里，方便对好友 ID 做提示与复制。这是一份纯本地备忘，与访问控制（管理员/白名单/黑名单）互不影响。" />
      <Table<Contact>
        rowKey="klei_id" size="small" columns={columns} dataSource={rows} loading={isLoading}
        pagination={rows.length > 20 ? { pageSize: 20 } : false}
        locale={{ emptyText: <Empty description="还没有记录。等有玩家加入游戏后会自动出现在这里。" /> }}
      />
    </Card>
  );
}
