import { theme, type ThemeConfig } from "antd";

/**
 * 视觉设计令牌 —— 依据 STYLE.md(OpenCode 风格):
 * 100% 等宽字体、暖米色画布、近黑墨色、纯平(无阴影)、交互元素 4px 圆角、容器 0/4px。
 * 仅描述视觉,不含任何业务逻辑。
 *
 * 提供亮色 / 暗色两套调色板,结构完全一致,供明暗切换使用。
 */
export interface Palette {
  // Surface
  canvas: string;
  surfaceSoft: string;
  surfaceCard: string;
  surfaceDark: string;
  surfaceDarkElevated: string;
  hairline: string;
  hairlineStrong: string;
  // Ink / Text
  ink: string;
  inkDeep: string;
  charcoal: string;
  body: string;
  mute: string;
  stone: string;
  ash: string;
  onDark: string;
  onPrimary: string;
  // Semantic (Apple HIG ramp)
  accent: string;
  danger: string;
  warning: string;
  success: string;
  // Console(日志终端面 —— 在任何模式下都是深色)
  console: string;
  consoleText: string;
  consoleBorder: string;
}

export const lightColors: Palette = {
  canvas: "#fdfcfc",
  surfaceSoft: "#f8f7f7",
  surfaceCard: "#f1eeee",
  surfaceDark: "#201d1d",
  surfaceDarkElevated: "#302c2c",
  hairline: "rgba(15, 0, 0, 0.12)",
  hairlineStrong: "#646262",
  ink: "#201d1d",
  inkDeep: "#0f0000",
  charcoal: "#302c2c",
  body: "#424245",
  mute: "#646262",
  stone: "#6e6e73",
  ash: "#9a9898",
  onDark: "#fdfcfc",
  onPrimary: "#fdfcfc",
  accent: "#007aff",
  danger: "#ff3b30",
  warning: "#ff9f0a",
  success: "#30d158",
  console: "#201d1d",
  consoleText: "#fdfcfc",
  consoleBorder: "#302c2c",
};

export const darkColors: Palette = {
  canvas: "#201d1d",
  surfaceSoft: "#2a2626",
  surfaceCard: "#322e2e",
  surfaceDark: "#161313",
  surfaceDarkElevated: "#2a2626",
  hairline: "rgba(253, 252, 252, 0.14)",
  hairlineStrong: "#8b8989",
  ink: "#fdfcfc",
  inkDeep: "#ffffff",
  charcoal: "#e4e1e1",
  body: "#cfcccc",
  mute: "#9a9898",
  stone: "#878585",
  ash: "#6e6e73",
  onDark: "#fdfcfc",
  onPrimary: "#201d1d",
  accent: "#0a84ff",
  danger: "#ff453a",
  warning: "#ff9f0a",
  success: "#32d74b",
  console: "#161313",
  consoleText: "#e4e1e1",
  consoleBorder: "#2a2626",
};

/** 兼容旧引用:默认指向亮色调色板。 */
export const COLORS = lightColors;

/**
 * 等宽字体栈 —— Berkeley Mono 优先,回退到 JetBrains Mono 等开源近似字体,
 * 末尾追加彩色 emoji 字体,保证特殊字符 / 表情符号正常显示而非豆腐块。
 */
export const MONO =
  '"Berkeley Mono", "JetBrains Mono", "IBM Plex Mono", ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace, "Apple Color Emoji", "Segoe UI Emoji", "Noto Color Emoji"';

function buildAntdTheme(p: Palette, isDark: boolean): ThemeConfig {
  return {
    algorithm: isDark ? theme.darkAlgorithm : theme.defaultAlgorithm,
    token: {
      colorPrimary: p.ink,
      colorInfo: p.accent,
      colorSuccess: p.success,
      colorWarning: p.warning,
      colorError: p.danger,
      colorLink: p.ink,
      colorLinkHover: p.charcoal,
      colorLinkActive: p.inkDeep,

      colorTextBase: p.ink,
      colorText: p.ink,
      colorTextSecondary: p.mute,
      colorTextTertiary: p.stone,
      colorTextDescription: p.mute,

      colorBgBase: p.canvas,
      colorBgContainer: p.canvas,
      colorBgElevated: p.canvas,
      colorBgLayout: p.canvas,
      colorBgSpotlight: p.surfaceDark,

      colorBorder: p.hairline,
      colorBorderSecondary: p.hairline,

      fontFamily: MONO,
      fontFamilyCode: MONO,
      fontSize: 14,

      // 纯平:系统中没有任何投影
      boxShadow: "none",
      boxShadowSecondary: "none",
      boxShadowTertiary: "none",

      // 圆角词汇:交互元素 4px
      borderRadius: 4,
      borderRadiusLG: 4,
      borderRadiusSM: 4,
      borderRadiusXS: 4,

      wireframe: false,
    },
    components: {
      Layout: {
        headerBg: p.canvas,
        siderBg: p.canvas,
        bodyBg: p.canvas,
        headerHeight: 56,
        headerPadding: "0 20px",
      },
      Menu: {
        itemBg: "transparent",
        subMenuItemBg: "transparent",
        itemColor: p.mute,
        itemSelectedColor: p.ink,
        itemSelectedBg: p.surfaceCard,
        itemHoverColor: p.ink,
        itemHoverBg: p.surfaceSoft,
        itemActiveBg: p.surfaceCard,
        itemBorderRadius: 4,
      },
      Button: {
        primaryShadow: "none",
        defaultShadow: "none",
        dangerShadow: "none",
        colorTextLightSolid: p.onPrimary,
        fontWeight: 500,
      },
      Card: {
        colorBgContainer: p.canvas,
        borderRadiusLG: 4,
        boxShadowTertiary: "none",
      },
      Modal: {
        contentBg: p.canvas,
        headerBg: p.canvas,
        borderRadiusLG: 4,
      },
      Drawer: {
        colorBgElevated: p.canvas,
      },
      Table: {
        headerBg: p.surfaceSoft,
        headerColor: p.ink,
        borderColor: p.hairline,
        rowHoverBg: p.surfaceSoft,
        colorBgContainer: p.canvas,
        headerSplitColor: p.hairline,
      },
      Input: {
        colorBgContainer: p.surfaceSoft,
        activeBg: p.canvas,
        borderRadius: 4,
        activeBorderColor: p.ink,
        hoverBorderColor: p.hairlineStrong,
        activeShadow: "none",
      },
      InputNumber: {
        colorBgContainer: p.surfaceSoft,
        activeBorderColor: p.ink,
        hoverBorderColor: p.hairlineStrong,
        activeShadow: "none",
      },
      Select: {
        colorBgContainer: p.surfaceSoft,
        optionSelectedBg: p.surfaceCard,
        optionSelectedColor: p.ink,
        activeBorderColor: p.ink,
        hoverBorderColor: p.hairlineStrong,
        activeOutlineColor: "transparent",
      },
      Tag: {
        defaultBg: p.surfaceSoft,
        defaultColor: p.ink,
        borderRadiusSM: 4,
      },
      Tabs: {
        inkBarColor: p.ink,
        itemColor: p.mute,
        itemSelectedColor: p.ink,
        itemHoverColor: p.ink,
      },
      Breadcrumb: {
        itemColor: p.mute,
        lastItemColor: p.ink,
        linkColor: p.mute,
        linkHoverColor: p.ink,
        separatorColor: p.stone,
        fontSize: 13,
      },
      Tooltip: {
        colorBgSpotlight: p.surfaceDark,
        colorTextLightSolid: p.onDark,
      },
    },
  };
}

export const lightTheme = buildAntdTheme(lightColors, false);
export const darkTheme = buildAntdTheme(darkColors, true);

/** 兼容旧引用:默认导出亮色主题。 */
export const antdTheme = lightTheme;
