import { PlusOutlined, SearchOutlined } from "@ant-design/icons";
import { Button, Empty, Image, Input, Modal, Space, Table, Tag, Typography, message } from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useState } from "react";
import { useAddMod, useSearchMods } from "../../api/hooks";
import type { WorkshopSearchResult } from "../../api/types";

const fmtSize = (n: number) => {
  if (!n) return "—";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0, v = n;
  while (v >= 1024 && i < u.length - 1) { v /= 1024; i++; }
  return `${v.toFixed(v >= 10 || i === 0 ? 0 : 1)} ${u[i]}`;
};

/** 搜索 Workshop MOD(输入 ID 或名称)→ 展示已确认存在的结果 → 点击「添加」加入实例。 */
export function ModSearchModal(
  { instanceId, existingIds, open, onClose }:
  { instanceId: number; existingIds: Set<string>; open: boolean; onClose: () => void },
) {
  const [q, setQ] = useState("");
  const [results, setResults] = useState<WorkshopSearchResult[] | null>(null);
  const [added, setAdded] = useState<Set<string>>(new Set());
  const search = useSearchMods();
  const add = useAddMod();

  const doSearch = async () => {
    const text = q.trim();
    if (!text) return;
    try {
      const r = await search.mutateAsync(text);
      setResults(r);
      if (!r.length) message.info("没有找到匹配的 MOD,换个关键词或确认 ID 是否正确");
    } catch (e) { message.error((e as Error).message); }
  };

  const doAdd = async (m: WorkshopSearchResult) => {
    try {
      await add.mutateAsync({ id: instanceId, workshop_id: m.workshop_id, name: m.title });
      setAdded((s) => new Set(s).add(m.workshop_id));
      message.success(`已添加:${m.title || m.workshop_id}`);
    } catch (e) { message.error((e as Error).message); }
  };

  const close = () => {
    setQ(""); setResults(null); setAdded(new Set());
    onClose();
  };

  const columns: ColumnsType<WorkshopSearchResult> = [
    {
      title: "预览", width: 80, render: (_, m) => (m.preview_url
        ? <Image src={m.preview_url} width={56} height={56} style={{ objectFit: "cover", borderRadius: 4 }} />
        : <div style={{ width: 56, height: 56, background: "#f1eeee", borderRadius: 4 }} />),
    },
    {
      title: "MOD", render: (_, m) => (
        <Space direction="vertical" size={2}>
          <Typography.Text strong ellipsis style={{ maxWidth: 320 }}>{m.title || "(无标题)"}</Typography.Text>
          <Space size={4} wrap>
            <Tag color="blue" style={{ marginInlineEnd: 0 }}>{m.workshop_id}</Tag>
            <Typography.Link href={`https://steamcommunity.com/sharedfiles/filedetails/?id=${m.workshop_id}`}
              target="_blank" style={{ fontSize: 12 }}>创意工坊页 ↗</Typography.Link>
          </Space>
        </Space>
      ),
    },
    {
      title: "更新时间", width: 120, render: (_, m) =>
        m.time_updated ? dayjs.unix(m.time_updated).format("YYYY-MM-DD") : "—",
    },
    { title: "大小", width: 90, render: (_, m) => fmtSize(m.file_size) },
    {
      title: "操作", width: 110, render: (_, m) => {
        const has = existingIds.has(m.workshop_id) || added.has(m.workshop_id);
        return has
          ? <Tag color="success">已添加</Tag>
          : <Button size="small" type="primary" icon={<PlusOutlined />}
              loading={add.isPending} onClick={() => doAdd(m)}>添加</Button>;
      },
    },
  ];

  return (
    <Modal title="搜索并添加 MOD" open={open} onCancel={close} footer={null} width={760} destroyOnClose>
      <Space direction="vertical" style={{ width: "100%" }} size="middle">
        <Input.Search
          placeholder="输入 Workshop ID(如 378160973)或名称(如 Global Positions)"
          enterButton={<><SearchOutlined /> 搜索</>}
          allowClear value={q} loading={search.isPending}
          onChange={(e) => setQ(e.target.value)} onSearch={doSearch}
        />
        {results !== null && (
          <Table
            rowKey="workshop_id" size="small" columns={columns} dataSource={results}
            pagination={false} scroll={{ x: "max-content", y: 380 }}
            locale={{ emptyText: <Empty description="无结果" /> }}
          />
        )}
      </Space>
    </Modal>
  );
}
