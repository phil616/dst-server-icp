// 与玩法/风格相关的取值 ↔ 中文标签映射(单一事实来源,供表单选项与展示复用)。

export interface LabeledOption {
  value: string;
  label: string;
}

/** 游戏模式(玩法风格,DST play style)。顺序与游戏内主机界面一致。
 *  relaxed/lightsout 为有效值;wilderness/endless 在新版被引擎按 survival 兜底,但仍接受。 */
export const GAME_MODES: LabeledOption[] = [
  { value: "relaxed", label: "轻松" },
  { value: "survival", label: "生存" },
  { value: "endless", label: "无尽" },
  { value: "wilderness", label: "荒野" },
  { value: "lightsout", label: "暗无天日" },
];

/** 服务器风格 / 意图(cluster_intention)。 */
export const CLUSTER_INTENTIONS: LabeledOption[] = [
  { value: "cooperative", label: "合作" },
  { value: "competitive", label: "竞争" },
  { value: "social", label: "社交" },
  { value: "madness", label: "疯狂" },
];

const labelOf = (opts: LabeledOption[], v: string): string =>
  opts.find((o) => o.value === v)?.label ?? v;

/** 把 game_mode 取值翻成中文(未知值原样返回)。 */
export const gameModeLabel = (v: string): string => labelOf(GAME_MODES, v);
/** 把 cluster_intention 取值翻成中文(未知值原样返回)。 */
export const intentionLabel = (v: string): string => labelOf(CLUSTER_INTENTIONS, v);
