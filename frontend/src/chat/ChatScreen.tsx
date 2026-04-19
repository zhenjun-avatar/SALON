import { useCallback, useState } from "react";
import { FurnishingPicker } from "@/furnishing/FurnishingPicker";
import { ProductCatalog } from "@/furnishing/ProductCatalog";
import { resolveInternalToken } from "@/salon/config";
import { MessageList } from "./MessageList";
import { Composer } from "./Composer";
import { useChatSession } from "./useChatSession";
import styles from "./ChatScreen.module.css";

function mergeOutgoing(ids: string[], text: string): string {
  const idPart = ids.join(" ").trim();
  const t = text.trim();
  return [idPart, t].filter(Boolean).join(" ").trim();
}

type MainView = "chat" | "products";

export function ChatScreen() {
  const internalOk = Boolean(resolveInternalToken());
  const [mainView, setMainView] = useState<MainView>("chat");
  const [selectedAssetIds, setSelectedAssetIds] = useState<string[]>([]);
  const {
    messages,
    pendingFileId,
    loading,
    error,
    send,
    pickImage,
    clearPendingFile,
  } = useChatSession();

  const sendWithAssets = useCallback(
    (text: string) => {
      const merged = mergeOutgoing(selectedAssetIds, text);
      void send(merged);
      setSelectedAssetIds([]);
    },
    [send, selectedAssetIds],
  );

  const removeId = useCallback((id: string) => {
    setSelectedAssetIds((prev) => prev.filter((x) => x !== id));
  }, []);

  return (
    <div className={styles.shell}>
      <header className={styles.header}>
        <div className={styles.headerMain}>
          <h1 className={styles.title}>AI代理 · 家居</h1>
          <nav className={styles.tabs} role="tablist" aria-label="功能切换">
            <button
              type="button"
              role="tab"
              aria-selected={mainView === "chat"}
              className={`${styles.tab} ${mainView === "chat" ? styles.tabActive : ""}`}
              onClick={() => setMainView("chat")}
            >
              对话
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mainView === "products"}
              className={`${styles.tab} ${mainView === "products" ? styles.tabActive : ""}`}
              onClick={() => setMainView("products")}
            >
              产品列表
            </button>
          </nav>
        </div>
        {!internalOk ? (
          <div className={styles.headerRight}>
            <p className={styles.internalHint}>
              配置 <code>VITE_SALON_INTERNAL_TOKEN</code>（与网关 <code>SALON_INTERNAL_BOOKING_TOKEN</code>{" "}
              一致）可启用对话侧栏与产品列表数据。
            </p>
          </div>
        ) : null}
      </header>
      {error && mainView === "chat" ? <div className={styles.banner}>{error}</div> : null}
      <main className={styles.main}>
        {mainView === "products" ? (
          <div className={styles.catalogHost}>
            <ProductCatalog />
          </div>
        ) : (
          <div className={`${styles.layout} ${internalOk ? "" : styles.layoutSingle}`}>
            {internalOk ? (
              <div className={styles.pickerCol}>
                <FurnishingPicker
                  selectedIds={selectedAssetIds}
                  onChangeSelectedIds={setSelectedAssetIds}
                />
              </div>
            ) : null}
            <div className={styles.chatCol}>
              <MessageList messages={messages} />
              <Composer
                disabled={loading}
                pendingFileId={pendingFileId}
                attachedIds={selectedAssetIds}
                onRemoveAttachedId={removeId}
                onClearAttachedIds={() => setSelectedAssetIds([])}
                onSend={sendWithAssets}
                onPickFile={pickImage}
                onClearFile={clearPendingFile}
              />
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
