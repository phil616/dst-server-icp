import axios from "axios";

// 内网部署、无鉴权;同源访问后端。
export const http = axios.create({ baseURL: "/", timeout: 30000 });

http.interceptors.response.use(
  (r) => r,
  (err) => {
    const detail = err?.response?.data?.detail ?? err.message ?? "请求失败";
    return Promise.reject(new Error(String(detail)));
  },
);

/** 当前页面对应的 WebSocket 基址(支持反代/HTTPS)。 */
export function wsBase(): string {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${location.host}`;
}
