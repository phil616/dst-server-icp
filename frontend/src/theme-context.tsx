import { ConfigProvider } from "antd";
import zhCN from "antd/locale/zh_CN";
import {
  createContext, useContext, useEffect, useMemo, useState, type ReactNode,
} from "react";
import { darkColors, darkTheme, lightColors, lightTheme, type Palette } from "./theme";

export type ThemeMode = "light" | "dark";

interface ThemeCtx {
  mode: ThemeMode;
  colors: Palette;
  toggle: () => void;
}

const Ctx = createContext<ThemeCtx | null>(null);

/** 读取当前主题(明/暗)、对应调色板与切换方法。 */
export function useThemeMode(): ThemeCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useThemeMode 必须在 ThemeProvider 内使用");
  return v;
}

const STORAGE_KEY = "dst-theme-mode";

/** 主题提供者:管理明暗状态,持久化到 localStorage,并向 antd 注入对应主题。 */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [mode, setMode] = useState<ThemeMode>(() => {
    const saved = typeof localStorage !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
    return saved === "dark" ? "dark" : "light";
  });

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, mode);
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  const value = useMemo<ThemeCtx>(() => ({
    mode,
    colors: mode === "dark" ? darkColors : lightColors,
    toggle: () => setMode((m) => (m === "dark" ? "light" : "dark")),
  }), [mode]);

  return (
    <Ctx.Provider value={value}>
      <ConfigProvider locale={zhCN} theme={mode === "dark" ? darkTheme : lightTheme}>
        {children}
      </ConfigProvider>
    </Ctx.Provider>
  );
}
