import { useCallback, useState } from "react";
import type { ChatMessage } from "@/salon/types";
import { useSalonClient } from "@/salon/SalonClientContext";
import { mergeAnswerChunk, pickStreamHint } from "./difyStream";
import { loadOrCreateFromUser, saveFromUser } from "./ids";

function uid() {
  return crypto.randomUUID();
}

/**
 * Chat state + send/upload。
 * 优先走 Dify 流式（与 Dify 网页类似的增量输出）；失败时回退阻塞接口。
 */
export function useChatSession() {
  const client = useSalonClient();
  const [fromUser, setFromUser] = useState(loadOrCreateFromUser);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pendingFileId, setPendingFileId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setUserId = useCallback((id: string) => {
    const t = id.trim();
    setFromUser(t);
    saveFromUser(t);
  }, []);

  const send = useCallback(
    async (content: string) => {
      const trimmed = content.trim();
      if (!trimmed && !pendingFileId) return;
      setError(null);
      const userLine: ChatMessage = {
        id: uid(),
        role: "user",
        content: trimmed || "（图片）",
      };
      const assistantId = uid();
      const assistantPlaceholder: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
        streamHint: "连接网关…",
      };
      setMessages((m) => [...m, userLine, assistantPlaceholder]);
      setLoading(true);
      const fileId = pendingFileId;
      setPendingFileId(null);

      const applyAssistant = (patch: Partial<ChatMessage>) => {
        setMessages((prev) =>
          prev.map((msg) => (msg.id === assistantId ? { ...msg, ...patch } : msg)),
        );
      };

      try {
        let accumulated = "";
        const errBox: { err: Error | null } = { err: null };
        try {
          await client.sendWecomTextStream(
            {
              from_user: fromUser,
              content: trimmed,
              upload_file_id: fileId,
            },
            (d) => {
              if (d.event === "error") {
                errBox.err = new Error(String(d.message || "Dify 流式错误"));
                return;
              }
              const hint = pickStreamHint(d);
              if (typeof d.answer === "string") {
                accumulated = mergeAnswerChunk(accumulated, d.answer);
                applyAssistant({
                  content: accumulated,
                  ...(hint ? { streamHint: hint } : {}),
                });
              } else if (hint) {
                applyAssistant({ streamHint: hint });
              }
            },
          );
          if (errBox.err) throw errBox.err;
          applyAssistant({
            content: (accumulated || "").trim() || "（无回复）",
            streaming: false,
            streamHint: undefined,
          });
        } catch {
          const reply = await client.sendWecomText({
            from_user: fromUser,
            content: trimmed,
            upload_file_id: fileId,
          });
          applyAssistant({
            content: (reply || "").trim() || "（无回复）",
            streaming: false,
            streamHint: undefined,
          });
        }
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
        setMessages((m) => [
          ...m.filter((x) => x.id !== assistantId),
          { id: uid(), role: "system", content: `发送失败：${msg}` },
        ]);
      } finally {
        setLoading(false);
      }
    },
    [client, fromUser, pendingFileId],
  );

  const pickImage = useCallback(
    async (file: File | null) => {
      if (!file) return;
      setError(null);
      setLoading(true);
      try {
        const { upload_file_id } = await client.uploadImage(file, fromUser);
        setPendingFileId(upload_file_id);
      } catch (e) {
        const msg = e instanceof Error ? e.message : String(e);
        setError(msg);
      } finally {
        setLoading(false);
      }
    },
    [client, fromUser],
  );

  const clearPendingFile = useCallback(() => setPendingFileId(null), []);

  return {
    fromUser,
    setUserId,
    messages,
    pendingFileId,
    loading,
    error,
    send,
    pickImage,
    clearPendingFile,
  };
}
