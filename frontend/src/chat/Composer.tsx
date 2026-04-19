import { useRef, useState, type FormEvent } from "react";
import styles from "./Composer.module.css";

type Props = {
  disabled: boolean;
  pendingFileId: string | null;
  attachedIds: string[];
  onRemoveAttachedId: (id: string) => void;
  onClearAttachedIds: () => void;
  onSend: (text: string) => void;
  onPickFile: (file: File | null) => void;
  onClearFile: () => void;
};

export function Composer({
  disabled,
  pendingFileId,
  attachedIds,
  onRemoveAttachedId,
  onClearAttachedIds,
  onSend,
  onPickFile,
  onClearFile,
}: Props) {
  const [text, setText] = useState("");
  const fileRef = useRef<HTMLInputElement>(null);

  function submit(e: FormEvent) {
    e.preventDefault();
    if (disabled) return;
    const t = text.trim();
    if (!t && !pendingFileId && attachedIds.length === 0) return;
    onSend(text);
    setText("");
  }

  return (
    <form className={styles.form} onSubmit={submit}>
      {attachedIds.length > 0 ? (
        <div className={styles.attachRow}>
          <span className={styles.attachLabel}>将发送素材</span>
          {attachedIds.map((id) => (
            <span key={id} className={styles.assetChip}>
              {id}
              <button
                type="button"
                className={styles.chipX}
                aria-label={`移除 ${id}`}
                onClick={() => onRemoveAttachedId(id)}
              >
                ×
              </button>
            </span>
          ))}
          <button type="button" className={styles.clearAttach} onClick={onClearAttachedIds}>
            清空
          </button>
        </div>
      ) : null}
      <div className={styles.bar}>
      <input
        ref={fileRef}
        type="file"
        accept="image/*"
        className={styles.fileHidden}
        onChange={(e) => {
          onPickFile(e.target.files?.[0] ?? null);
          e.target.value = "";
        }}
      />
      <button
        type="button"
        className={styles.iconBtn}
        disabled={disabled}
        onClick={() => fileRef.current?.click()}
        title="上传图片"
      >
        图
      </button>
      <textarea
        className={styles.input}
        rows={2}
        placeholder="输入消息…"
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit(e);
          }
        }}
      />
      <button type="submit" className={styles.send} disabled={disabled}>
        发送
      </button>
      {pendingFileId ? (
        <span className={styles.chip}>
          已选图
          <button type="button" className={styles.chipX} onClick={onClearFile}>
            ×
          </button>
        </span>
      ) : null}
      </div>
    </form>
  );
}
