import { useFormatter as useIntlFormatter, useLocale } from "next-intl";

const NUMERIC_DATE = { day: "2-digit", month: "2-digit", year: "numeric" } as const;
const NUMERIC_TIME = { hour: "2-digit", minute: "2-digit" } as const;

/** Казахский формат даты (ДД.ММ.ГГГГ, как принято в РК) — числовой, через русские шаблоны. */
export function kazakhDateTime(value: Date | number, options?: Intl.DateTimeFormatOptions): string {
  const withTime = Boolean(
    options && (options.timeStyle !== undefined || options.hour !== undefined),
  );
  return new Intl.DateTimeFormat("ru-RU", {
    ...NUMERIC_DATE,
    ...(withTime ? NUMERIC_TIME : {}),
    timeZone: options?.timeZone,
  }).format(value);
}

/**
 * `useFormatter` из next-intl с поправкой для казахского: в ICU браузеров и Node нет шаблонов
 * дат для kk, и `dateStyle` выдаёт «2026 M10 28». Числа форматируются как обычно.
 */
export function useFormatter(): ReturnType<typeof useIntlFormatter> {
  const format = useIntlFormatter();
  const locale = useLocale();
  if (locale !== "kk") return format;
  // Подменяется только dateTime; сигнатура совместима для используемых вызовов (Date + options)
  return {
    ...format,
    dateTime: ((value: Date | number, options?: Intl.DateTimeFormatOptions) =>
      kazakhDateTime(value, options)) as typeof format.dateTime,
  };
}
