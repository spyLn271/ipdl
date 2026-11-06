"use client";

import { useTranslations } from "next-intl";
import { cn } from "@/lib/utils";

/** Ссылки «S3, S7» на карточки источников внизу страницы. */
export function SourceRefs({ ids, className }: { ids: readonly string[]; className?: string }) {
  const t = useTranslations("portrait");
  const unique = [...new Set(ids)];
  if (unique.length === 0) return null;
  return (
    <span className={cn("inline-flex flex-wrap items-center gap-1", className)}>
      <span className="sr-only">{t("sourcesRef")}:</span>
      {unique.slice(0, 8).map((id) => (
        <a
          key={id}
          href={`#source-${id}`}
          className="rounded-[4px] bg-bg-subtle px-1.5 py-0.5 font-mono text-[11px] leading-none text-fg hover:bg-accent-subtle hover:text-info-fg"
        >
          {id}
        </a>
      ))}
    </span>
  );
}
