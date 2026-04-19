# Salon 聊天前端（React + Vite）

对接 `salon_gateway` 的 `POST /simulate/wecom-text` 与 `POST /simulate/upload-image`（开发联调）。

## 本地运行

1. 复制环境变量：`cp .env.example .env`（Windows 可手动复制），填写 `VITE_SALON_SIMULATE_TOKEN`。
2. **方式 A**：在 `.env` 写 `VITE_SALON_API_BASE=https://你的域名/salon`（需网关允许浏览器 CORS）。
3. **方式 B**：写 `VITE_DEV_PROXY_TARGET=http://127.0.0.1:8765`（与 `python -m salon_gateway` 默认端口一致；若改了 `SALON_PORT` 则同步改这里），`VITE_SALON_API_BASE` 留空则使用默认 `/salon` 走 Vite 代理。代理会把 `/salon/...` **重写为** 网关根路径上的 `...`（本地 uvicorn 没有 `/salon` 前缀）。
4. 另开终端在项目里启动网关：`cd src/agent && python -m salon_gateway`（默认 `http://127.0.0.1:8765`）。
5. `npm install` → `npm run dev`（修改 `vite.config.ts` 或 `.env` 后请重启 dev）。

`from_user` 会持久化在 `localStorage`，与上传图片、Dify 会话一致。

## 扩展

- 生产鉴权：新增网关路由 + JWT，前端实现第二个 `SalonClient` 或给 `SalonClient` 增加 `authMode`。
- 流式：扩展 `sendWecomText` 为 SSE，在 `useChatSession` 中追加 token 而非整段替换。
