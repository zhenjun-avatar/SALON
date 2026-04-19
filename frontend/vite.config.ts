import path from "node:path";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const proxyTarget = env.VITE_DEV_PROXY_TARGET?.trim();

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "src") },
    },
    server: {
      port: 5173,
      proxy: proxyTarget
        ? {
            // 浏览器仍用 /salon/*（与线上一致）；本机网关默认挂在根路径，需去掉 /salon 前缀再转发
            "/salon": {
              target: proxyTarget,
              changeOrigin: true,
              rewrite: (p) => p.replace(/^\/salon/, "") || "/",
            },
          }
        : undefined,
    },
  };
});
