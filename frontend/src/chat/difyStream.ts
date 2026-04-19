/** 合并 Dify 流式 ``answer``：有的版本为增量，有的为累计全文。 */
export function mergeAnswerChunk(accumulated: string, chunk: string): string {
  if (!chunk) return accumulated;
  if (!accumulated) return chunk;
  if (chunk.startsWith(accumulated)) return chunk;
  if (accumulated.startsWith(chunk)) return accumulated;
  if (accumulated.endsWith(chunk)) return accumulated;
  return accumulated + chunk;
}

/** 从 SSE JSON 里取一行状态提示（工作流 / 节点名等）。 */
export function pickStreamHint(d: Record<string, unknown>): string | undefined {
  const ev = String(d.event ?? "");
  const nested =
    typeof d.data === "object" && d.data !== null
      ? (d.data as Record<string, unknown>)
      : undefined;
  const title =
    (nested?.title as string | undefined) ||
    (nested?.node_title as string | undefined) ||
    (d.title as string | undefined);
  if (title?.trim()) return title.trim();
  if (ev === "workflow_started") return "工作流已启动";
  if (ev.includes("node_started")) return "执行编排节点…";
  if (ev === "message" || ev === "agent_message") return "正在生成回复…";
  if (ev === "message_end" || ev === "ping") return undefined;
  if (ev) return ev.replace(/_/g, " ");
  return undefined;
}
