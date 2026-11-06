/** Форматирование значений портрета (без React — легко тестировать). */
import { type JobStatus, type RiskLevel } from "@/lib/api/schemas";

export type Tone = "ok" | "warning" | "error" | "neutral";

/** Низкий риск — зелёный, средний — оранжевый, высокий — красный, «нет данных» — серый. */
export function levelTone(level: RiskLevel | null | undefined): Tone {
  switch (level) {
    case "low":
      return "ok";
    case "medium":
      return "warning";
    case "high":
      return "error";
    default:
      return "neutral";
  }
}

/** Цвет графики (шкала, Gauge) для уровня риска — токены дизайн-системы. */
export const LEVEL_FILL: Record<RiskLevel, string> = {
  low: "var(--nc-ok)",
  medium: "var(--nc-warning)",
  high: "var(--nc-error)",
  no_data: "var(--nc-chart-8)",
};

/** Инициалы для заглушки фото: «Иванов Пётр Сергеевич» → «ИП». */
export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean);
  return words
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
}

/** Дата из источника может быть неполной: «2019», «2019-05» или «2019-05-14». */
export function formatPartialDate(value: string | null | undefined, locale: string): string {
  if (!value) return "";
  // В ICU нет шаблонов дат для kk («2026 M10 28») — для казахского числовой формат РК
  const intlLocale = locale === "kk" ? "ru-RU" : locale;
  const full = /^(\d{4})-(\d{2})-(\d{2})/.exec(value);
  if (full) {
    const date = new Date(Date.UTC(Number(full[1]), Number(full[2]) - 1, Number(full[3])));
    return date.toLocaleDateString(intlLocale, {
      timeZone: "UTC",
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
    });
  }
  const month = /^(\d{4})-(\d{2})$/.exec(value);
  if (month && locale === "kk") return `${month[2]}.${month[1]}`;
  if (month) {
    const date = new Date(Date.UTC(Number(month[1]), Number(month[2]) - 1, 1));
    return date.toLocaleDateString(locale, { timeZone: "UTC", month: "long", year: "numeric" });
  }
  return value;
}

/** «2019 — 2023», «с 2019», «по 2023». */
export function formatPeriod(
  start: string | null | undefined,
  end: string | null | undefined,
  locale: string,
  labels: { since: string; until: string; present: string },
  isCurrent?: boolean | null,
): string {
  const from = formatPartialDate(start, locale);
  const to = formatPartialDate(end, locale);
  if (from && to) return `${from} — ${to}`;
  if (from) return isCurrent ? `${from} — ${labels.present}` : `${labels.since} ${from}`;
  if (to) return `${labels.until} ${to}`;
  return isCurrent ? labels.present : "";
}

export function isFinal(status: JobStatus | null | undefined): boolean {
  return status === "done" || status === "failed";
}

export function isBuilding(status: JobStatus | null | undefined): boolean {
  return status === "queued" || status === "running";
}

/** Положение балла на шкале 0–100 (для маркера), с отступом от краёв. */
export function scalePosition(score: number): number {
  return Math.min(98, Math.max(2, Math.round(score)));
}
