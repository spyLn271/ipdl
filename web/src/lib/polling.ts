import { type PortraitOut } from "@/lib/api/schemas";
import { isFinal } from "@/lib/format";

export const POLL_MS = 2000;

/** Опрос строящейся версии: каждые 2 с, пока статус не финальный и нет ошибки (404/401 и т. п.). */
export function pollInterval(data: PortraitOut | undefined, error: unknown): number | false {
  if (error) return false;
  if (data && isFinal(data.meta.status)) return false;
  return POLL_MS;
}
