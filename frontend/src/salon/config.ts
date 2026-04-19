/** Salon gateway base path, e.g. `https://quizmesh.tech/salon` or `/salon` behind Vite proxy. */
export function resolveSalonApiBase(): string {
  const raw = (import.meta.env.VITE_SALON_API_BASE || "").trim().replace(/\/$/, "");
  return raw || "/salon";
}

export function resolveSimulateToken(): string {
  return (import.meta.env.VITE_SALON_SIMULATE_TOKEN || "").trim();
}

/** 与网关 `SALON_INTERNAL_BOOKING_TOKEN` 中任一段一致；用于 GET /internal/furnishing-assets（素材勾选）。 */
export function resolveInternalToken(): string {
  return (import.meta.env.VITE_SALON_INTERNAL_TOKEN || "").trim();
}
