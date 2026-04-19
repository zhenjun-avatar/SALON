import { createContext, useContext, useMemo, type ReactNode } from "react";
import { SalonClient } from "./SalonClient";
import { resolveInternalToken, resolveSalonApiBase, resolveSimulateToken } from "./config";

const SalonClientContext = createContext<SalonClient | null>(null);

export function SalonClientProvider({ children }: { children: ReactNode }) {
  const client = useMemo(() => {
    const apiBase = resolveSalonApiBase();
    const simulateToken = resolveSimulateToken();
    const internalToken = resolveInternalToken();
    return new SalonClient({
      apiBase,
      simulateToken,
      internalToken: internalToken || undefined,
    });
  }, []);

  return (
    <SalonClientContext.Provider value={client}>{children}</SalonClientContext.Provider>
  );
}

export function useSalonClient(): SalonClient {
  const c = useContext(SalonClientContext);
  if (!c) throw new Error("useSalonClient must be used within SalonClientProvider");
  return c;
}
