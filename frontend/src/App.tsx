import { SalonClientProvider } from "@/salon/SalonClientContext";
import { resolveSimulateToken } from "@/salon/config";
import { ChatScreen } from "@/chat/ChatScreen";
import styles from "./App.module.css";

export function App() {
  const missingToken = !resolveSimulateToken();

  return (
    <SalonClientProvider>
      {missingToken ? (
        <div className={styles.warn}>
          请在 <code>frontend/.env</code> 中设置{" "}
          <code>VITE_SALON_SIMULATE_TOKEN</code>（与网关 <code>SALON_SIMULATE_TOKEN</code>{" "}
          一致），并配置 <code>VITE_SALON_API_BASE</code> 或开发代理{" "}
          <code>VITE_DEV_PROXY_TARGET</code>。
        </div>
      ) : null}
      <ChatScreen />
    </SalonClientProvider>
  );
}
