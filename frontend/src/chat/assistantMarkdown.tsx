import { defaultUrlTransform } from "react-markdown";
import type { ImgHTMLAttributes } from "react";

/** 将 `&lt;img ...&gt;` 等还原为 `<`，便于后续提取标签。 */
export function decodeHtmlEntitiesForAssistant(raw: string): string {
  if (typeof document === "undefined") return raw;
  const t = document.createElement("textarea");
  t.innerHTML = raw;
  return t.value;
}

/**
 * `furnishing_assets.json` 常为公网 `https://quizmesh.tech/salon/furnishing-asset-files/…`。
 * 在 localhost 等环境直连该域名可能 `ERR_CONNECTION_CLOSED`；改为当前页同源路径，
 * 由 Vite `/salon` 代理到网关 `StaticFiles`（strip 后为 `/furnishing-asset-files/…`）。
 */
function rewriteSalonFurnishingAssetUrlToSameOrigin(url: string): string {
  if (typeof window === "undefined") return url;
  let parsed: URL;
  try {
    parsed = new URL(url);
  } catch {
    return url;
  }
  const p = parsed.pathname;
  if (!p.startsWith("/salon/furnishing-asset-files/")) return url;
  if (parsed.host === window.location.host) return url;
  return `${window.location.origin}${parsed.pathname}${parsed.search}${parsed.hash}`;
}

export function absolutizeMediaUrl(url: string): string {
  const u = url.trim();
  if (!u) return u;
  const proxied = /^https?:\/\//i.test(u) ? rewriteSalonFurnishingAssetUrlToSameOrigin(u) : u;
  if (/^https?:\/\//i.test(proxied)) return proxied;
  if (proxied.startsWith("//")) return `https:${proxied}`;
  if (proxied.startsWith("/") && typeof window !== "undefined") {
    return `${window.location.origin}${proxied}`;
  }
  return proxied;
}

/**
 * 在通过 defaultUrlTransform 后，把站内相对路径补成绝对地址，
 * 否则 Markdown 里 `![](/salon/...)` 在 `localhost:5173` 会指到本机而非网关。
 */
export function markdownUrlTransform(value: string): string {
  const d = defaultUrlTransform(value);
  if (!d) return "";
  return absolutizeMediaUrl(d);
}

function extractImgSrc(tag: string): string | undefined {
  const q = tag.match(/\bsrc\s*=\s*("([^"]*)"|'([^']*)'|&quot;([^&]*)&quot;|&#34;([^#]*)&#34;)/i);
  if (q) {
    const inner = (q[2] || q[3] || q[4] || q[5] || "").trim();
    if (inner) return inner;
  }
  const uq = tag.match(/\bsrc\s*=\s*([^\s>]+)/i);
  if (uq) return uq[1].replace(/^["']|["']$/g, "").trim() || undefined;
  return undefined;
}

function extractImgAlt(tag: string): string | undefined {
  const q = tag.match(/\balt\s*=\s*("([^"]*)"|'([^']*)'|&quot;([^&]*)&quot;)/i);
  if (q) {
    const inner = (q[2] || q[3] || q[4] || "").trim();
    if (inner) return inner;
  }
  return undefined;
}

function safeMdAlt(s: string): string {
  return s.replace(/\]/g, " ").replace(/\n/g, " ").trim().slice(0, 200) || "缩略图";
}

/** 含空格或括号时用尖括号包裹，符合 CommonMark 图片 destination。 */
function mdImageDestination(url: string): string {
  const u = url.trim();
  if (/[\s()]/.test(u)) return `<${u}>`;
  return u;
}

/**
 * Dify 里内联的 `<img>` 在 Markdown 里会当纯文本；先解码实体再转成 `![]()` 以便 react-markdown 出图。
 */
export function assistantContentForMd(raw: string): string {
  const text = decodeHtmlEntitiesForAssistant(raw);
  return text.replace(/<img\b[^>]*>/gi, (tag) => {
    const srcRaw = extractImgSrc(tag);
    if (!srcRaw) return "";
    const src = absolutizeMediaUrl(decodeHtmlEntitiesForAssistant(srcRaw));
    const alt = safeMdAlt(extractImgAlt(tag) || "缩略图");
    return `\n\n![${alt}](${mdImageDestination(src)})\n\n`;
  });
}

export function MarkdownImg(props: ImgHTMLAttributes<HTMLImageElement>) {
  const { src, alt, ...rest } = props;
  const resolved = typeof src === "string" ? absolutizeMediaUrl(src) : src;
  return (
    <img
      {...rest}
      src={resolved}
      alt={alt ?? ""}
      referrerPolicy="no-referrer"
      loading="lazy"
      decoding="async"
    />
  );
}
