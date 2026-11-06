import { ApiError } from "@/lib/api/errors";

/** Ключи переводов errors.* для известных кодов API; иначе — сообщение сервера. */
const KNOWN = new Set([
  "network",
  "invalid_response",
  "upstream_unavailable",
  "unauthenticated",
  "invalid_credentials",
  "locked",
  "forbidden",
  "not_found",
  "csrf_failed",
  "queue_full",
  "already_running",
  "not_ready",
  "duplicate",
  "weak_password",
  "invalid_password",
  "self_lockout",
]);

export function errorMessage(error: unknown, t: (key: string) => string): string {
  if (error instanceof ApiError) {
    if (KNOWN.has(error.code)) return t(`errors.codes.${error.code}`);
    if (error.message && !error.message.startsWith("http_")) return error.message;
  }
  return t("errors.generic");
}
