import axios from "axios";
import { apiKeyHeader, clearApiKey, openApiKeyDialog } from "./cookies";

// 同源访问后端;鉴权用 APIKey 头(值取自 Cookie,无字段则为空串,但头一定存在)。
export const http = axios.create({ baseURL: "/", timeout: 30000 });

// 请求:始终附带 APIKey 头(后端架构约定:即使未启用保护也读此头)。
http.interceptors.request.use((config) => {
  config.headers.set("APIKey", apiKeyHeader());
  return config;
});

http.interceptors.response.use(
  (r) => r,
  (err) => {
    // 401:APIKey 失效/缺失 —— 清掉本地 Cookie 并弹出鉴权页重新索要。
    if (err?.response?.status === 401) {
      clearApiKey();
      openApiKeyDialog();
    }
    const detail = err?.response?.data?.detail ?? err.message ?? "请求失败";
    return Promise.reject(new Error(String(detail)));
  },
);

/** 当前页面对应的 WebSocket 基址(支持反代/HTTPS)。 */
export function wsBase(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
}
