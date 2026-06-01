// Cookie 持久化 + APIKey 鉴权事件。
// 约定:APIKey 存于 Cookie,默认 14 天过期。区分「字段不存在(undefined)」与「字段为空("")」——
// 前者表示从未验证,需弹出鉴权页;后者(含未启用保护时)视为已就绪。

const API_KEY_COOKIE = "APIKey";
const COOKIE_DAYS = 14;

/** 读取 Cookie:字段不存在返回 undefined,存在(含空值)返回字符串。 */
export function getCookie(name: string): string | undefined {
  const m = document.cookie.match(new RegExp("(?:^|;\\s*)" + name + "=([^;]*)"));
  return m ? decodeURIComponent(m[1]) : undefined;
}

export function setCookie(name: string, value: string, days = COOKIE_DAYS): void {
  const expires = new Date(Date.now() + days * 864e5).toUTCString();
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`;
}

export function deleteCookie(name: string): void {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; SameSite=Lax`;
}

// ---- APIKey 专用 ----
export const getApiKey = (): string | undefined => getCookie(API_KEY_COOKIE);
/** 总是返回可直接放进 HTTP 头的字符串:无字段时为空串。 */
export const apiKeyHeader = (): string => getApiKey() ?? "";
export const saveApiKey = (value: string): void => setCookie(API_KEY_COOKIE, value);
export const clearApiKey = (): void => deleteCookie(API_KEY_COOKIE);

// ---- 鉴权页打开事件(供非 React 的 axios 拦截器 / 布局按钮触发 AuthGate)----
export const AUTH_OPEN_EVENT = "dstd:auth-open";
export function openApiKeyDialog(): void {
  window.dispatchEvent(new Event(AUTH_OPEN_EVENT));
}
