const USER_KEY = "salon_chat_from_user";

export function loadOrCreateFromUser(): string {
  try {
    const v = localStorage.getItem(USER_KEY)?.trim();
    if (v) return v;
  } catch {
    /* ignore */
  }
  const id = `web-${crypto.randomUUID().slice(0, 8)}`;
  try {
    localStorage.setItem(USER_KEY, id);
  } catch {
    /* ignore */
  }
  return id;
}

export function saveFromUser(id: string) {
  try {
    localStorage.setItem(USER_KEY, id.trim());
  } catch {
    /* ignore */
  }
}
