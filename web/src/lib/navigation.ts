/** Куда вернуться после входа: только относительный путь внутри сайта (защита от open redirect). */
export function safeNext(value: string | null): string {
  if (!value || !value.startsWith("/") || value.startsWith("//") || value.startsWith("/\\")) {
    return "/";
  }
  return value;
}
