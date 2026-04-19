import { useEffect, useMemo, useRef, useState } from "react";
import type { FurnishingAsset } from "@/salon/types";
import { useSalonClient } from "@/salon/SalonClientContext";
import { absolutizeMediaUrl } from "@/chat/assistantMarkdown";
import { resolveInternalToken } from "@/salon/config";
import { IconCart, IconCartPlus, IconMinus, IconPlus } from "./ShopIcons";
import styles from "./ProductCatalog.module.css";

const FETCH_LIMIT = 100;
const QTY_MAX = 99;

function clampQty(n: number): number {
  if (!Number.isFinite(n)) return 1;
  return Math.min(QTY_MAX, Math.max(1, Math.floor(n)));
}

export function ProductCatalog() {
  const client = useSalonClient();
  const internalOk = Boolean(resolveInternalToken());
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [category, setCategory] = useState("");
  const [items, setItems] = useState<FurnishingAsset[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  /** 在无分类筛选时合并接口返回的分类，避免筛完只剩一类后下拉被清空 */
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const [preview, setPreview] = useState<{ url: string; title: string } | null>(null);
  /** 加入购物车前在卡片上选择的数量（默认 1） */
  const [lineQty, setLineQty] = useState<Record<string, number>>({});
  /** 本地购物车：sku id → 件数（尚未对接结算） */
  const [cart, setCart] = useState<Record<string, number>>({});
  const [cartOpen, setCartOpen] = useState(false);
  const cartPanelRef = useRef<HTMLDivElement>(null);

  const cartTotalQty = useMemo(
    () => Object.values(cart).reduce((s, n) => s + (n > 0 ? n : 0), 0),
    [cart],
  );

  const bumpLineQty = (id: string, delta: number) => {
    setLineQty((prev) => {
      const cur = prev[id] ?? 1;
      return { ...prev, [id]: clampQty(cur + delta) };
    });
  };

  const setLineQtyFor = (id: string, raw: number) => {
    setLineQty((prev) => ({ ...prev, [id]: clampQty(raw) }));
  };

  const addToCart = (asset: FurnishingAsset) => {
    const q = clampQty(lineQty[asset.id] ?? 1);
    setCart((c) => ({ ...c, [asset.id]: (c[asset.id] ?? 0) + q }));
    setLineQty((prev) => ({ ...prev, [asset.id]: 1 }));
  };

  useEffect(() => {
    if (!cartOpen) return;
    const onDown = (e: MouseEvent) => {
      const el = cartPanelRef.current;
      if (el && !el.contains(e.target as Node)) setCartOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [cartOpen]);

  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 280);
    return () => window.clearTimeout(t);
  }, [q]);

  useEffect(() => {
    if (!internalOk) {
      setErr(null);
      setItems([]);
      setTotal(0);
      setLoading(false);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setErr(null);
    client
      .listFurnishingAssets({
        q: debouncedQ,
        category: category.trim() || undefined,
        limit: FETCH_LIMIT,
      })
      .then((r) => {
        if (!cancelled) {
          setItems(r.items);
          setTotal(r.total);
          if (!category.trim()) {
            setCategoryOptions((prev) => {
              const s = new Set(prev);
              for (const it of r.items) {
                if (it.category?.trim()) s.add(it.category.trim());
              }
              return [...s].sort();
            });
          }
        }
      })
      .catch((e) => {
        if (!cancelled) {
          const msg = e instanceof Error ? e.message : String(e);
          setErr(msg);
          setItems([]);
          setTotal(0);
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [client, debouncedQ, category, internalOk]);

  useEffect(() => {
    if (!preview) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPreview(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [preview]);

  if (!internalOk) {
    return (
      <div className={styles.wrap}>
        <p className={styles.err}>
          请配置 <code>VITE_SALON_INTERNAL_TOKEN</code>（与网关 <code>SALON_INTERNAL_BOOKING_TOKEN</code> 一致）后刷新，即可加载产品素材。
        </p>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <div className={styles.toolbar}>
        <input
          className={styles.search}
          type="search"
          placeholder="按名称、标签、id 搜索…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          spellCheck={false}
          aria-label="搜索素材"
        />
        <select
          className={styles.catSelect}
          value={category}
          onChange={(e) => setCategory(e.target.value)}
          aria-label="按分类筛选"
        >
          <option value="">全部分类</option>
          {categoryOptions.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
        <div className={styles.toolbarEnd}>
          <div className={styles.shopToolbar} ref={cartPanelRef}>
            <button
              type="button"
              className={styles.cartBtn}
              onClick={() => setCartOpen((o) => !o)}
              aria-expanded={cartOpen}
              aria-haspopup="dialog"
              title={cartTotalQty ? `购物车内共 ${cartTotalQty} 件` : "购物车"}
            >
              <IconCart className={styles.cartBtnIcon} />
              <span>购物车</span>
              <span className={styles.cartBadge} aria-label={`共 ${cartTotalQty} 件`}>
                {cartTotalQty > QTY_MAX ? `${QTY_MAX}+` : cartTotalQty}
              </span>
            </button>
            {cartOpen ? (
              <div className={styles.cartPanel} role="dialog" aria-label="购物车预览">
                {cartTotalQty === 0 ? (
                  <p className={styles.cartPanelEmpty}>购物车还是空的</p>
                ) : (
                  <ul className={styles.cartPanelList}>
                    {Object.entries(cart)
                      .filter(([, n]) => n > 0)
                      .map(([id, n]) => {
                        const it = items.find((x) => x.id === id);
                        const label = it?.name ? `${it.name}` : id;
                        return (
                          <li key={id} className={styles.cartPanelRow}>
                            <span className={styles.cartPanelTitle}>{label}</span>
                            <span className={styles.cartPanelMeta}>
                              <code className={styles.cartPanelId}>{id}</code>
                              <span className={styles.cartPanelQty}>×{n}</span>
                            </span>
                          </li>
                        );
                      })}
                  </ul>
                )}
                {cartTotalQty > 0 ? (
                  <button type="button" className={styles.cartClear} onClick={() => setCart({})}>
                    清空
                  </button>
                ) : null}
              </div>
            ) : null}
          </div>
          <span className={styles.meta}>
            共 {total} 条
            {total > FETCH_LIMIT ? `（当前最多拉取 ${FETCH_LIMIT} 条）` : null}
          </span>
        </div>
      </div>
      {err ? (
        <p className={styles.err} role="alert">
          加载失败：{err}
        </p>
      ) : null}
      <div className={styles.grid}>
        {loading ? <div className={styles.loading}>加载中…</div> : null}
        {!loading &&
          items.map((a, idx) => (
            <article key={a.id} className={styles.card}>
              <div className={styles.thumbWrap}>
                {a.image_url ? (
                  <button
                    type="button"
                    className={styles.thumbBtn}
                    onClick={() =>
                      setPreview({
                        url: absolutizeMediaUrl(a.image_url),
                        title: `${a.id}${a.name ? ` · ${a.name}` : ""}`,
                      })
                    }
                    aria-label={`查看大图：${a.id}`}
                  >
                    <img
                      className={styles.thumb}
                      src={absolutizeMediaUrl(a.image_url)}
                      alt=""
                      loading={idx < 12 ? "eager" : "lazy"}
                      decoding="async"
                      referrerPolicy="no-referrer"
                    />
                  </button>
                ) : (
                  <div className={styles.placeholder} aria-hidden />
                )}
              </div>
              <div className={styles.body}>
                <div className={styles.id}>{a.id}</div>
                {a.category ? <div className={styles.category}>{a.category}</div> : null}
                <div className={styles.name}>{a.name || "—"}</div>
                {a.tags?.length ? (
                  <div className={styles.tags}>
                    {a.tags.map((t) => (
                      <span key={t} className={styles.tag}>
                        {t}
                      </span>
                    ))}
                  </div>
                ) : null}
                <div className={styles.cardShop}>
                  <div className={styles.qtyRow}>
                    <span className={styles.qtyLabel} id={`qty-label-${a.id}`}>
                      数量
                    </span>
                    <div className={styles.qtyStepper} role="group" aria-labelledby={`qty-label-${a.id}`}>
                      <button
                        type="button"
                        className={styles.qtyBtn}
                        onClick={() => bumpLineQty(a.id, -1)}
                        disabled={(lineQty[a.id] ?? 1) <= 1}
                        aria-label="减少数量"
                      >
                        <IconMinus className={styles.qtyBtnIcon} />
                      </button>
                      <input
                        className={styles.qtyInput}
                        type="text"
                        inputMode="numeric"
                        autoComplete="off"
                        maxLength={2}
                        value={String(lineQty[a.id] ?? 1)}
                        onChange={(e) => {
                          const digits = e.target.value.replace(/\D/g, "").slice(0, 2);
                          if (digits === "") {
                            setLineQty((prev) => ({ ...prev, [a.id]: 1 }));
                            return;
                          }
                          setLineQtyFor(a.id, parseInt(digits, 10));
                        }}
                        onBlur={() => setLineQtyFor(a.id, lineQty[a.id] ?? 1)}
                        aria-label={`${a.id} 购买数量，1–${QTY_MAX}`}
                      />
                      <button
                        type="button"
                        className={styles.qtyBtn}
                        onClick={() => bumpLineQty(a.id, 1)}
                        disabled={(lineQty[a.id] ?? 1) >= QTY_MAX}
                        aria-label="增加数量"
                      >
                        <IconPlus className={styles.qtyBtnIcon} />
                      </button>
                    </div>
                  </div>
                  <button
                    type="button"
                    className={styles.addToCart}
                    onClick={() => addToCart(a)}
                    title={`将 ${lineQty[a.id] ?? 1} 件加入购物车`}
                  >
                    <IconCartPlus className={styles.addToCartIcon} />
                    <span>加入购物车</span>
                  </button>
                </div>
              </div>
            </article>
          ))}
      </div>
      {preview ? (
        <div
          className={styles.lightbox}
          role="dialog"
          aria-modal="true"
          aria-label="图片预览"
          onClick={() => setPreview(null)}
        >
          <div className={styles.lightboxCard} onClick={(e) => e.stopPropagation()}>
            <button
              type="button"
              className={styles.lightboxClose}
              aria-label="关闭预览"
              onClick={() => setPreview(null)}
            >
              ×
            </button>
            <img
              className={styles.lightboxImg}
              src={preview.url}
              alt={preview.title}
              referrerPolicy="no-referrer"
            />
            <p className={styles.lightboxCaption}>{preview.title}</p>
          </div>
        </div>
      ) : null}
    </div>
  );
}
