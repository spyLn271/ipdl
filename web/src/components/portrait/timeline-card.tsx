"use client";

import { useLocale, useTranslations } from "next-intl";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { SourceRefs } from "@/components/portrait/source-refs";
import { type TimelineEvent } from "@/lib/api/schemas";
import { formatPartialDate } from "@/lib/format";
import { cn } from "@/lib/utils";

const KIND_DOT: Record<string, string> = {
  position: "bg-accent",
  adverse: "bg-error",
  legal: "bg-warning",
};

export function TimelineCard({ events }: { events: readonly TimelineEvent[] }) {
  const t = useTranslations("portrait");
  const locale = useLocale();
  // Новые события сверху, но не больше 20 — полная хронология есть в экспорте
  const shown = [...events].reverse().slice(0, 20);
  return (
    <SectionCard title={t("timelineTitle")} titleId="timeline-title">
      {shown.length === 0 ? (
        <p className="text-sm text-fg-muted">{t("timelineEmpty")}</p>
      ) : (
        <ul>
          {shown.map((event, index) => (
            <Row key={`${event.date}-${index}`} className="justify-start">
              <span className="w-24 shrink-0 font-mono text-xs leading-5 text-fg">
                {formatPartialDate(event.date, locale)}
              </span>
              <span
                aria-hidden
                className={cn(
                  "mt-1.5 size-2 shrink-0 rounded-full bg-border-strong",
                  KIND_DOT[event.kind],
                )}
              />
              <span className="min-w-0 flex-1 text-sm text-fg">{event.summary}</span>
              {event.source_id && <SourceRefs ids={[event.source_id]} className="shrink-0" />}
            </Row>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
