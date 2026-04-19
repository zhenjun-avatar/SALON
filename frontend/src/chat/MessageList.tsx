import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage } from "@/salon/types";
import { assistantContentForMd, markdownUrlTransform, MarkdownImg } from "./assistantMarkdown";
import styles from "./MessageList.module.css";

function Bubble({ m }: { m: ChatMessage }) {
  const isUser = m.role === "user";
  const isSystem = m.role === "system";
  const isAssistant = m.role === "assistant";
  return (
    <div
      className={`${styles.row} ${isUser ? styles.rowUser : ""} ${isSystem ? styles.rowSystem : ""}`}
    >
      <div
        className={`${styles.bubble} ${isUser ? styles.bubbleUser : ""} ${isSystem ? styles.bubbleSystem : ""} ${isAssistant && m.streaming ? styles.bubbleStreaming : ""}`}
      >
        {isAssistant ? (
          <>
            {m.streamHint ? <div className={styles.streamHint}>{m.streamHint}</div> : null}
            {m.streaming && !m.content.trim() ? (
              <div className={styles.typingRow} aria-live="polite">
                <span className={styles.typingDot} />
                <span className={styles.typingDot} />
                <span className={styles.typingDot} />
              </div>
            ) : null}
            {m.content.trim() ? (
              <div className={styles.md}>
                <Markdown
                  remarkPlugins={[remarkGfm]}
                  urlTransform={markdownUrlTransform}
                  components={{ img: MarkdownImg }}
                >
                  {assistantContentForMd(m.content)}
                </Markdown>
              </div>
            ) : null}
          </>
        ) : (
          <div className={styles.plain}>{m.content}</div>
        )}
      </div>
    </div>
  );
}

export function MessageList({ messages }: { messages: ChatMessage[] }) {
  return (
    <div className={styles.list}>
      {messages.length === 0 ? (
        <p className={styles.empty}>发送消息开始对话</p>
      ) : (
        messages.map((m) => <Bubble key={m.id} m={m} />)
      )}
    </div>
  );
}
