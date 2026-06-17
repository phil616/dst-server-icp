import {
  CloudDownloadOutlined, CloudSyncOutlined, DeleteOutlined, EditOutlined, PlusOutlined, ReloadOutlined,
  ToolOutlined,
} from "@ant-design/icons";
import {
  Alert, Button, Descriptions, Divider, Empty, Form, Input, InputNumber, Modal, Popconfirm, Select,
  Space, Switch, Table, Tag, Tooltip, Typography, message,
} from "antd";
import type { ColumnsType } from "antd/es/table";
import dayjs from "dayjs";
import { useEffect, useState } from "react";
import {
  useCheckModUpdates, useRemoveMod, useRepairLibrary, useTriggerModsUpdate,
  useTranslateModConfig, useTriggerOneModUpdate, useUpdateMod, waitForJob,
} from "../../api/hooks";
import type { Mod, ModConfigChoice, ModConfigOption, ModConfigTranslation, ModUpdateStatus } from "../../api/types";
import { useTaskQueue } from "../../task-queue-context";
import { ModSearchModal } from "./ModSearchModal";

const UPDATE_TAG: Record<ModUpdateStatus, { color: string; text: string }> = {
  latest: { color: "success", text: "最新" },
  outdated: { color: "error", text: "有更新" },
  unknown: { color: "default", text: "未知(请更新一次)" },
  unchecked: { color: "default", text: "未检查" },
  manual: { color: "blue", text: "手动 MOD" },
};

const EMPTY_TRANSLATION: ModConfigTranslation = { labels: {}, choices: {} };

/** 版本号格式化:纯数字版本(如 1.2.3)加 "v" 前缀;含空格/字母的字符串版本(部分 MOD 把
 *  整串塞进 modinfo 的 version 字段,如 "under the weather pt.1 v1.5.4.1")原样显示,不再被截断。 */
function fmtVersion(v: string): string {
  const s = (v || "").trim();
  if (!s) return "—";
  return /^\d/.test(s) ? `v${s}` : s;
}

/** 过长的版本号在标签里截断显示,完整内容交给 Tooltip 悬停展示。 */
function shortVersion(v: string, max = 14): string {
  const s = fmtVersion(v);
  return s.length > max ? `${s.slice(0, max).trimEnd()} …` : s;
}

function hasOwn(obj: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(obj, key);
}

function stableValue(v: unknown): unknown {
  if (Array.isArray(v)) return v.map(stableValue);
  if (v !== null && typeof v === "object") {
    return Object.fromEntries(
      Object.entries(v as Record<string, unknown>)
        .sort(([a], [b]) => a.localeCompare(b))
        .map(([key, val]) => [key, stableValue(val)]),
    );
  }
  return v;
}

function valueKey(v: unknown): string {
  const s = JSON.stringify(stableValue(v));
  return s === undefined ? "undefined" : s;
}

function parseValueKey(v: string): unknown {
  if (v === "undefined") return undefined;
  return JSON.parse(v);
}

function valuesEqual(a: unknown, b: unknown): boolean {
  return valueKey(a) === valueKey(b);
}

function displayConfigValue(v: unknown): string {
  if (v === undefined) return "未设置";
  if (v === null) return "nil";
  if (typeof v === "boolean") return v ? "true" : "false";
  if (typeof v === "string") return v || "\"\"";
  if (typeof v === "number") return String(v);
  return valueKey(v);
}

function editableValue(v: unknown): unknown {
  if (Array.isArray(v) || (v !== null && typeof v === "object")) return JSON.stringify(v, null, 2);
  return v;
}

function parseEditableValue(v: unknown, sample: unknown): unknown {
  if (typeof sample === "boolean") return Boolean(v);
  if (typeof sample === "number") return typeof v === "number" ? v : Number(v);
  if (Array.isArray(sample) || (sample !== null && typeof sample === "object")) {
    return typeof v === "string" ? JSON.parse(v) : v;
  }
  return v ?? "";
}

function resolveOptionValue(option: ModConfigOption, config: Record<string, unknown>) {
  if (hasOwn(config, option.name)) return { value: config[option.name], source: "saved" as const };
  if (option.has_default) return { value: option.default, source: "default" as const };
  return { value: undefined, source: "unset" as const };
}

function optionValue(option: ModConfigOption, config: Record<string, unknown>): unknown {
  return resolveOptionValue(option, config).value;
}

function initialConfigValues(mod: Mod): Record<string, unknown> {
  const values: Record<string, unknown> = {};
  for (const option of mod.config_schema.options) {
    const current = resolveOptionValue(option, mod.config);
    if (current.source !== "unset") {
      values[option.name] = option.options.length ? valueKey(current.value) : editableValue(current.value);
    }
  }
  const known = new Set(mod.config_schema.options.map((o) => o.name));
  for (const [key, value] of Object.entries(mod.config)) {
    if (!known.has(key)) values[key] = editableValue(value);
  }
  return values;
}

function jsonRule() {
  return {
    validator: async (_rule: unknown, value: unknown) => {
      if (value === undefined || value === "") return;
      if (typeof value !== "string") return;
      JSON.parse(value);
    },
  };
}

function buildConfigFromForm(mod: Mod, formConfig: Record<string, unknown>): Record<string, unknown> {
  const next: Record<string, unknown> = {};
  const known = new Set(mod.config_schema.options.map((o) => o.name));

  for (const option of mod.config_schema.options) {
    const raw = formConfig[option.name];
    if (raw === undefined && !hasOwn(mod.config, option.name)) continue;
    const choices = new Map(option.options.map((choice) => [valueKey(choice.data), choice.data]));
    const rawKey = String(raw);
    const parsed = option.options.length
      ? choices.get(rawKey) ?? parseValueKey(rawKey)
      : parseEditableValue(raw, optionValue(option, mod.config));
    if (hasOwn(mod.config, option.name) || !option.has_default || !valuesEqual(parsed, option.default)) {
      next[option.name] = parsed;
    }
  }

  for (const [key, value] of Object.entries(mod.config)) {
    if (known.has(key)) continue;
    next[key] = parseEditableValue(formConfig[key], value);
  }

  return next;
}

function translatedOptionLabel(option: ModConfigOption, translation: ModConfigTranslation) {
  const original = option.label || option.name;
  const translated = translation.labels[option.name];
  if (!translated) return original;
  return (
    <Space size={6} wrap>
      <span>{translated}</span>
      <Typography.Text type="secondary">{original}</Typography.Text>
    </Space>
  );
}

function translatedChoiceLabel(
  option: ModConfigOption | undefined, choice: ModConfigChoice, translation: ModConfigTranslation,
) {
  const original = choice.description || displayConfigValue(choice.data);
  if (!option) return original;
  const translated = translation.choices[option.name]?.[valueKey(choice.data)];
  return translated ? `${translated} (${original})` : original;
}

function optionTooltip(option: ModConfigOption, translation: ModConfigTranslation): string {
  const translated = translation.labels[option.name];
  const original = option.label || option.name;
  return [translated ? `原文:${original}` : "", option.hover].filter(Boolean).join("\n") || option.name;
}

function mergeTranslation(prev: ModConfigTranslation, next: ModConfigTranslation): ModConfigTranslation {
  return {
    labels: { ...prev.labels, ...next.labels },
    choices: { ...prev.choices, ...next.choices },
  };
}

function configEntriesForDisplay(mod: Mod) {
  const entries = mod.config_schema.options.map((option) => {
    const resolved = resolveOptionValue(option, mod.config);
    return {
      key: option.name,
      label: option.label || option.name,
      value: resolved.value,
      source: resolved.source,
    };
  });
  const known = new Set(mod.config_schema.options.map((option) => option.name));
  for (const [key, value] of Object.entries(mod.config)) {
    if (!known.has(key)) entries.push({ key, label: key, value, source: "saved" as const });
  }
  return entries;
}

function sourceTag(source: "saved" | "default" | "unset") {
  if (source === "saved") return <Tag color="success">已保存</Tag>;
  if (source === "default") return <Tag color="blue">默认</Tag>;
  return <Tag color="default">未设置</Tag>;
}

function ConfigValueInput(
  { option, value, translation }: {
    option?: ModConfigOption; value: unknown; translation: ModConfigTranslation;
  },
) {
  if (option?.options.length) {
    const currentKey = value === undefined ? "" : valueKey(value);
    const seen = new Set<string>();
    const selectOptions = option.options.map((choice) => {
      const key = valueKey(choice.data);
      seen.add(key);
      return {
        value: key,
        label: translatedChoiceLabel(option, choice, translation),
        title: choice.hover || displayConfigValue(choice.data),
      };
    });
    if (currentKey && !seen.has(currentKey)) {
      selectOptions.push({ value: currentKey, label: displayConfigValue(value), title: displayConfigValue(value) });
    }
    return <Select allowClear options={selectOptions} placeholder="未设置" />;
  }
  if (typeof value === "boolean") return <Switch />;
  if (typeof value === "number") return <InputNumber style={{ width: "100%" }} />;
  if (Array.isArray(value) || (value !== null && typeof value === "object")) {
    return <Input.TextArea autoSize={{ minRows: 2, maxRows: 6 }} />;
  }
  return <Input />;
}

function ModConfigModal(
  { instanceId, mod, onClose }: { instanceId: number; mod: Mod | null; onClose: () => void },
) {
  const [form] = Form.useForm();
  const update = useUpdateMod();
  const translate = useTranslateModConfig();
  const schemaOptions = mod?.config_schema.options ?? [];
  const [translation, setTranslation] = useState<ModConfigTranslation>(EMPTY_TRANSLATION);
  const [translating, setTranslating] = useState<"labels" | "choices" | null>(null);

  useEffect(() => {
    if (!mod) return;
    setTranslation(EMPTY_TRANSLATION);
    form.setFieldsValue({
      config: initialConfigValues(mod),
      raw: JSON.stringify(mod.config, null, 2),
    });
  }, [form, mod]);

  const save = async () => {
    if (!mod) return;
    try {
      const values = await form.validateFields();
      const config = schemaOptions.length
        ? buildConfigFromForm(mod, values.config ?? {})
        : JSON.parse(values.raw || "{}");
      await update.mutateAsync({ id: instanceId, workshopId: mod.workshop_id, config });
      message.success("MOD 配置已保存");
      onClose();
    } catch (e) {
      if ((e as { errorFields?: unknown[] }).errorFields) return;
      message.error((e as Error).message);
    }
  };

  const runTranslate = async (target: "labels" | "choices") => {
    if (!mod) return;
    setTranslating(target);
    try {
      const result = await translate.mutateAsync({ id: instanceId, workshopId: mod.workshop_id, target });
      setTranslation((prev) => mergeTranslation(prev, result));
      message.success(target === "labels" ? "配置项已翻译" : "配置值已翻译");
    } catch (e) {
      message.error((e as Error).message);
    } finally {
      setTranslating(null);
    }
  };

  const known = new Set(schemaOptions.map((o) => o.name));
  const extraEntries = mod ? Object.entries(mod.config).filter(([key]) => !known.has(key)) : [];
  const hasChoices = schemaOptions.some((option) => option.options.length > 0);

  return (
    <Modal
      title={mod ? `配置 ${mod.title || mod.name || mod.ref}` : "配置 MOD"}
      open={!!mod}
      onCancel={onClose}
      onOk={save}
      okText="保存"
      confirmLoading={update.isPending}
      destroyOnClose
      width={720}
    >
      {!mod ? null : (
        <Form form={form} layout="vertical">
          {schemaOptions.length ? (
            <>
              <Space wrap style={{ marginBottom: 12 }}>
                <Button
                  size="small"
                  disabled={translating !== null}
                  loading={translating === "labels"}
                  onClick={() => runTranslate("labels")}
                >
                  翻译配置项
                </Button>
                <Button
                  size="small"
                  disabled={!hasChoices || translating !== null}
                  loading={translating === "choices"}
                  onClick={() => runTranslate("choices")}
                >
                  翻译配置值
                </Button>
              </Space>
              {schemaOptions.map((option) => {
                const value = optionValue(option, mod.config);
                const isSwitch = !option.options.length && typeof value === "boolean";
                const isJson = !option.options.length
                  && (Array.isArray(value) || (value !== null && typeof value === "object"));
                return (
                  <Form.Item
                    key={option.name}
                    name={["config", option.name]}
                    label={translatedOptionLabel(option, translation)}
                    tooltip={optionTooltip(option, translation)}
                    valuePropName={isSwitch ? "checked" : "value"}
                    rules={isJson ? [jsonRule()] : undefined}
                  >
                    <ConfigValueInput option={option} value={value} translation={translation} />
                  </Form.Item>
                );
              })}
              {extraEntries.length ? (
                <>
                  <Divider orientation="left">其它配置</Divider>
                  {extraEntries.map(([key, value]) => {
                    const isSwitch = typeof value === "boolean";
                    const isJson = Array.isArray(value) || (value !== null && typeof value === "object");
                    return (
                      <Form.Item
                        key={key}
                        name={["config", key]}
                        label={key}
                        valuePropName={isSwitch ? "checked" : "value"}
                        rules={isJson ? [jsonRule()] : undefined}
                      >
                        <ConfigValueInput value={value} translation={translation} />
                      </Form.Item>
                    );
                  })}
                </>
              ) : null}
            </>
          ) : (
            <>
              <Typography.Text type="secondary">
                {mod.config_schema.installed ? "该 MOD 没有声明 configuration_options" : "该 MOD 尚未安装到 server/mods"}
              </Typography.Text>
              <Form.Item name="raw" style={{ marginTop: 12 }} rules={[jsonRule()]}>
                <Input.TextArea autoSize={{ minRows: 8, maxRows: 14 }} />
              </Form.Item>
            </>
          )}
          {mod.config_schema.error ? <Alert type="warning" message={mod.config_schema.error} /> : null}
        </Form>
      )}
    </Modal>
  );
}

/** MOD 管理:增删 / 启停 / 看配置 / 检查更新 / 一键更新 / 确认是否真正加载到游戏。 */
export function ModManager({ instanceId, mods }: { instanceId: number; mods: Mod[] }) {
  const [searchOpen, setSearchOpen] = useState(false);
  const [updatingWid, setUpdatingWid] = useState<string | null>(null);  // 单 MOD 更新中的 workshop_id
  const [configuring, setConfiguring] = useState<Mod | null>(null);
  const remove = useRemoveMod();
  const update = useUpdateMod();
  const check = useCheckModUpdates();
  const triggerUpdate = useTriggerModsUpdate();
  const triggerOne = useTriggerOneModUpdate();
  const repair = useRepairLibrary();
  const taskQueue = useTaskQueue();

  const hasUpdates = mods.some((m) => m.update_status === "outdated");
  const existingIds = new Set(mods.map((m) => m.workshop_id));

  const doCheck = async () => {
    try { await check.mutateAsync(instanceId); message.success("已检查更新"); }
    catch (e) { message.error((e as Error).message); }
  };
  const doUpdate = async () => {
    try {
      const j = await triggerUpdate.mutateAsync(instanceId);
      taskQueue.open();  // 触发更新即弹出任务队列,可见排队/执行状态
      message.info(`更新作业 #${j.id} 进行中…(缺 Steam 库会自动修复;实时输出见“系统日志”)`);
      const done = await waitForJob(j.id);
      if (done.status === "success") message.success("MOD 更新成功");
      else message.error(`MOD 更新失败:${done.error || "见系统日志"}`, 8);
    } catch (e) { message.error((e as Error).message); }
  };

  const doUpdateOne = async (wid: string) => {
    setUpdatingWid(wid);
    try {
      const j = await triggerOne.mutateAsync({ id: instanceId, workshopId: wid });
      taskQueue.open();  // 触发更新即弹出任务队列,可见排队/执行状态
      message.info(`MOD ${wid} 单独下载/更新作业 #${j.id} 进行中…(仅下载此 MOD,不影响其他)`);
      const done = await waitForJob(j.id);
      if (done.status === "success") message.success(`MOD ${wid} 下载/更新成功`);
      else message.error(`MOD ${wid} 下载/更新失败:${done.error || "见系统日志"}`, 8);
    } catch (e) { message.error((e as Error).message); }
    finally { setUpdatingWid(null); }
  };

  const doRepair = async () => {
    try {
      const j = await repair.mutateAsync();
      message.info(`修复作业 #${j.id} 进行中…(SteamCMD 校验安装,可能较久)`);
      const done = await waitForJob(j.id);
      if (done.status === "success") message.success("Steam 库已修复/校验完成");
      else message.error(`修复失败:${done.error || "见系统日志"}`, 8);
    } catch (e) { message.error((e as Error).message); }
  };

  const columns: ColumnsType<Mod> = [
    {
      title: "MOD", render: (_, m) => (
        <Space direction="vertical" size={0}>
          <Tag color="blue" style={{ marginInlineEnd: 0 }}>{m.ref}</Tag>
          <span>{m.title || m.name || "—"}</span>
        </Space>
      ),
    },
    {
      title: "已加载到游戏", render: (_, m) => {
        const shards = Object.entries(m.loaded);
        if (!shards.length) return <Tag color="default">未加载</Tag>;
        return shards.map(([shard, info]) => (
          <Tooltip key={shard} title={`${info.name} ${fmtVersion(info.version)}`}>
            <Tag color={info.status === "loaded" ? "success" : "error"}>
              {shard}: {info.status === "loaded" ? `✓ ${shortVersion(info.version)}` : "✗ 失败"}
            </Tag>
          </Tooltip>
        ));
      },
    },
    {
      title: "更新状态", render: (_, m) => {
        const t = UPDATE_TAG[m.update_status];
        const when = m.workshop_time_updated
          ? dayjs.unix(m.workshop_time_updated).format("YYYY-MM-DD") : "";
        return <Tooltip title={when && `Workshop 最近更新:${when}`}><Tag color={t.color}>{t.text}</Tag></Tooltip>;
      },
    },
    {
      title: "配置项", render: (_, m) => {
        const defined = m.config_schema.options.length;
        const current = Object.keys(m.config).length;
        return (
          <Space size={6}>
            <Tag color={defined ? "blue" : current ? "default" : "default"}>{defined || current}</Tag>
            <Button size="small" icon={<EditOutlined />} onClick={() => setConfiguring(m)}>配置</Button>
          </Space>
        );
      },
    },
    { title: "启用", render: (_, m) => <Switch checked={m.enabled} size="small"
        onChange={async (v) => { try { await update.mutateAsync({ id: instanceId, workshopId: m.workshop_id, enabled: v }); } catch (e) { message.error((e as Error).message); } }} /> },
    {
      title: "操作", width: 180, render: (_, m) => {
        const outdated = m.update_status === "outdated";
        const busy = updatingWid === m.workshop_id;
        return (
          <Space>
            <Tooltip title="单独下载/更新此 MOD(用 SteamCMD 仅拉取该 MOD,不影响其他;完成后看“已加载到游戏”确认是否载入)">
              <Button size="small"
                type={outdated ? "primary" : "default"} danger={outdated}
                icon={<CloudDownloadOutlined />}
                loading={busy}
                disabled={updatingWid !== null && !busy}
                onClick={() => doUpdateOne(m.workshop_id)}>
                {outdated ? "更新" : "下载/更新"}
              </Button>
            </Tooltip>
            <Popconfirm title="移除该 MOD?"
              onConfirm={async () => { await remove.mutateAsync({ id: instanceId, workshopId: m.workshop_id }); message.success("已移除"); }}>
              <Button size="small" danger icon={<DeleteOutlined />} />
            </Popconfirm>
          </Space>
        );
      },
    },
  ];

  return (
    <Space direction="vertical" style={{ width: "100%" }} size="middle">
      <Alert type="info" banner
        message="“已加载到游戏”来自服务器日志的 Loading mod 行(需服务器运行,确认真正载入而非仅下载完成);“更新状态”经 Steam Workshop API 比对更新时间。更新前会自动预检并修复 Steam 库(解决 “library folder not found” 导致的下载失败),成功/失败均有提示。" />
      <Space wrap>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setSearchOpen(true)}>搜索添加 MOD</Button>
        <Button icon={<ReloadOutlined />} loading={check.isPending} onClick={doCheck}>检查更新</Button>
        <Button type="primary" ghost danger={hasUpdates} icon={<CloudSyncOutlined />}
          loading={triggerUpdate.isPending} onClick={doUpdate}>
          {hasUpdates ? "更新全部(有新版)" : "更新全部(自动修复)"}
        </Button>
        <Tooltip title="单独校验/修复 Steam 库与服务端安装(SteamCMD validate)。当出现 “library folder not found” 或下载一直失败时使用。">
          <Button icon={<ToolOutlined />} loading={repair.isPending} onClick={doRepair}>修复 Steam 库</Button>
        </Tooltip>
      </Space>
      <Table
        rowKey="id" size="small" dataSource={mods} columns={columns} pagination={false}
        locale={{ emptyText: "暂无 MOD" }}
        expandable={{
          rowExpandable: (m) => configEntriesForDisplay(m).length > 0,
          expandedRowRender: (m) => {
            const entries = configEntriesForDisplay(m);
            return entries.length ? (
              <Descriptions size="small" column={2} bordered title="configuration_options">
                {entries.map((entry) => (
                  <Descriptions.Item key={entry.key} label={entry.label}>
                    <Space size={6} wrap>
                      <span>{displayConfigValue(entry.value)}</span>
                      {sourceTag(entry.source)}
                    </Space>
                  </Descriptions.Item>
                ))}
              </Descriptions>
            ) : <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无配置项" />;
          },
        }}
      />
      <ModSearchModal instanceId={instanceId} existingIds={existingIds}
        open={searchOpen} onClose={() => setSearchOpen(false)} />
      <ModConfigModal instanceId={instanceId} mod={configuring} onClose={() => setConfiguring(null)} />
    </Space>
  );
}
