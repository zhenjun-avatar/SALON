import { useCallback, useEffect, useMemo, useState } from "react";
import type { FurnishingAsset } from "@/salon/types";
import { useSalonClient } from "@/salon/SalonClientContext";
import { absolutizeMediaUrl } from "@/chat/assistantMarkdown";
import styles from "./FurnishingPicker.module.css";

const MAX = 4;

type Props = {
  selectedIds: string[];
  onChangeSelectedIds: (ids: string[]) => void;
};

export function FurnishingPicker({ selectedIds, onChangeSelectedIds }: Props) {
  const client = useSalonClient();
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [items, setItems] = useState<FurnishingAsset[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 320);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    client
      .listFurnishingAssets({ q: debouncedQ, limit: 100 })
      .then((r) => {
        if (!cancelled) setItems(r.items);
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setErr(msg);
          setItems([]);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, debouncedQ]);

  const selectedSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  const toggle = useCallback(
    (id: string) => {
      if (selectedSet.has(id)) {
        onChangeSelectedIds(selectedIds.filter((x) => x !== id));
        return;
      }
      if (selectedIds.length >= MAX) return;
      onChangeSelectedIds([...selectedIds, id]);
    },
    [onChangeSelectedIds, selectedIds, selectedSet],
  );

  return (
    <aside className={styles.wrap}>
      <h2 className={styles.title}>可选产品</h2>
      <input
        className={styles.search}
        type="search"
        placeholder="筛选名称 / 标签 / id…"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        spellCheck={false}
      />
      {err ? (
        <p className={styles.err} role="alert">
          加载失败：{err}
        </p>
      ) : null}
      <div className={styles.grid}>
        {loading ? <div className={styles.loading}>加载中…</div> : null}
        {!loading &&
          items.map((a, idx) => {
            const on = selectedSet.has(a.id);
            const full = !on && selectedIds.length >= MAX;
            const order = on ? selectedIds.indexOf(a.id) + 1 : 0;
            return (
              <button
                key={a.id}
                type="button"
                className={`${styles.card} ${on ? styles.cardSelected : ""} ${full ? styles.cardDisabled : ""}`}
                disabled={full}
                onClick={() => toggle(a.id)}
                title={a.name || a.id}
              >
                <div className={styles.cardInner}>
                  <div className={styles.thumbWrap}>
                    {on ? <span className={styles.badge}>{order}</span> : null}
                    {a.image_url ? (
                      <img
                        className={styles.thumb}
                        src={absolutizeMediaUrl(a.image_url)}
                        alt=""
                        loading={idx < 6 ? "eager" : "lazy"}
                        decoding="async"
                        referrerPolicy="no-referrer"
                      />
                    ) : (
                      <div className={styles.thumbPlaceholder} aria-hidden />
                    )}
                  </div>
                  <div className={styles.meta}>
                    <div className={styles.id}>{a.id}</div>
                    <div className={styles.name}>{a.name || "—"}</div>
                  </div>
                </div>
              </button>
            );
          })}
      </div>
    </aside>
  );
}
