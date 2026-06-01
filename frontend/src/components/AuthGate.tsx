import { KeyOutlined } from "@ant-design/icons";
import { Alert, Button, Card, Form, Input, Layout, Space, Typography, message } from "antd";
import { useEffect, useState } from "react";
import { authRequired, verifyApiKey } from "../api/endpoints";
import { AUTH_OPEN_EVENT, getApiKey, saveApiKey } from "../api/cookies";
import { useThemeMode } from "../theme-context";

type Phase = "loading" | "app" | "auth";

/**
 * 鉴权门:
 * - Cookie 有 APIKey 字段 → 直接进入应用。
 * - Cookie 无该字段 → 询问后端是否启用保护:不保护则写入空串放行,保护则弹出独立鉴权页。
 * - 任意请求 401 → axios 拦截器清 Cookie 并广播 AUTH_OPEN_EVENT,这里切回鉴权页。
 */
export function AuthGate({ children }: { children: React.ReactNode }) {
  const [phase, setPhase] = useState<Phase>(() => (getApiKey() !== undefined ? "app" : "loading"));

  useEffect(() => {
    let alive = true;
    if (phase === "loading") {
      authRequired()
        .then(({ required }) => {
          if (!alive) return;
          if (required) {
            setPhase("auth");
          } else {
            saveApiKey(""); // 未启用保护:写入空串,使 Cookie 字段存在,后续不再打扰
            setPhase("app");
          }
        })
        .catch(() => alive && setPhase("auth"));
    }
    return () => {
      alive = false;
    };
  }, [phase]);

  useEffect(() => {
    const open = () => setPhase("auth");
    window.addEventListener(AUTH_OPEN_EVENT, open);
    return () => window.removeEventListener(AUTH_OPEN_EVENT, open);
  }, []);

  if (phase === "auth") {
    return <AuthPage hasExistingKey={getApiKey() !== undefined} onDone={() => setPhase("app")} />;
  }
  if (phase === "loading") return <FullScreen>正在检查鉴权…</FullScreen>;
  return <>{children}</>;
}

function FullScreen({ children }: { children: React.ReactNode }) {
  const { colors } = useThemeMode();
  return (
    <Layout style={{ minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: colors.canvas, color: colors.mute }}>
      {children}
    </Layout>
  );
}

function AuthPage({ hasExistingKey, onDone }: { hasExistingKey: boolean; onDone: () => void }) {
  const { colors } = useThemeMode();
  const [value, setValue] = useState<string>(() => getApiKey() ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    saveApiKey(value); // 先写 Cookie,验证请求会带上它
    try {
      await verifyApiKey();
      message.success("APIKey 已验证");
      onDone();
    } catch (e) {
      // 401 时拦截器已清掉 Cookie;这里仅提示
      setError((e as Error).message || "APIKey 验证失败");
    } finally {
      setSubmitting(false);
    }
  };

  const cancel = () => {
    // 仅在已有有效 Key(进入修改模式)时允许返回
    if (getApiKey() !== undefined) onDone();
  };

  return (
    <Layout style={{ minHeight: "100vh", display: "flex", alignItems: "center",
      justifyContent: "center", background: colors.canvas, padding: 16 }}>
      <Card style={{ width: 420, maxWidth: "100%" }}>
        <Space direction="vertical" size="middle" style={{ width: "100%" }}>
          <Typography.Title level={4} style={{ margin: 0 }}>
            <KeyOutlined /> 访问验证
          </Typography.Title>
          <Typography.Text type="secondary">
            本控制台已启用 APIKey 保护,请输入 APIKey 以继续。APIKey 将保存在浏览器 Cookie 中(14 天有效)。
          </Typography.Text>
          {error && <Alert type="error" showIcon message={error} />}
          <Form layout="vertical" onFinish={submit}>
            <Form.Item label="APIKey" style={{ marginBottom: 12 }}>
              <Input.Password
                autoFocus
                value={value}
                onChange={(e) => setValue(e.target.value)}
                placeholder="请输入 APIKey"
                onPressEnter={submit}
              />
            </Form.Item>
            <Space>
              <Button type="primary" htmlType="submit" loading={submitting}>
                验证并进入
              </Button>
              {hasExistingKey && <Button onClick={cancel}>取消</Button>}
            </Space>
          </Form>
        </Space>
      </Card>
    </Layout>
  );
}
