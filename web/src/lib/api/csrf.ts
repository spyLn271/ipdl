/** Имена должны совпадать с настройками бэкенда (AuthSettings.csrf_cookie / csrf_header). */
export const CSRF_COOKIE = "ipdl_csrf";
export const CSRF_HEADER = "X-CSRF-Token";

/** Значение CSRF-cookie (double-submit): сервер сверяет его с заголовком изменяющих запросов. */
export function readCsrfToken(
  cookie: string = typeof document === "undefined" ? "" : document.cookie,
): string {
  for (const part of cookie.split(";")) {
    const [name, ...rest] = part.trim().split("=");
    if (name === CSRF_COOKIE) return decodeURIComponent(rest.join("="));
  }
  return "";
}
