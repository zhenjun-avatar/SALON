export type ChatRole = "user" | "assistant" | "system";

export type ChatMessage = {
  id: string;
  role: ChatRole;
  content: string;
  /** 流式生成中（最后一条助手气泡） */
  streaming?: boolean;
  /** Dify 工作流 / 节点等过程提示 */
  streamHint?: string;
};

export type WecomSimulateResponse = {
  reply: string;
};

export type UploadImageResponse = {
  upload_file_id: string;
  filename: string;
  dify_user: string;
};

export type FurnishingAsset = {
  id: string;
  category: string;
  name: string;
  image_url: string;
  tags: string[];
};

export type FurnishingAssetsListResponse = {
  items: FurnishingAsset[];
  total: number;
};
