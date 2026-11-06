"use client";

import { Gavel, Newspaper } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { SourceRefs } from "@/components/portrait/source-refs";
import { type Portrait } from "@/lib/api/schemas";
import { formatPartialDate } from "@/lib/format";

const SEVERITY_TONE = { low: "neutral", medium: "warning", high: "error" } as const;

export function AdverseCard({ portrait }: { portrait: Portrait }) {
  const t = useTranslations();
  const locale = useLocale();
  const { adverse, legal } = portrait;
  return (
    <SectionCard title={t("portrait.adverseTitle")} titleId="adverse-title">
      {adverse.length === 0 && legal.length === 0 ? (
        <p className="text-sm text-fg-muted">{t("portrait.adverseEmpty")}</p>
      ) : (
        <ul>
          {adverse.map((item, index) => (
            <Row key={`a-${index}`}>
              <div className="flex min-w-0 gap-2">
                <Newspaper className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden />
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm text-fg">{item.summary}</span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
                    {item.date && (
                      <span className="font-mono">{formatPartialDate(item.date, locale)}</span>
                    )}
                    <span>{t(`severities.${item.severity}`)}</span>
                    <SourceRefs ids={item.evidence.map((e) => e.source_id)} />
                  </span>
                  {item.evidence[0] && (
                    <blockquote className="mt-1 border-l-2 border-border-strong pl-2 text-xs text-fg-muted italic">
                      «{item.evidence[0].quote}»
                    </blockquote>
                  )}
                </div>
              </div>
              <Badge tone={SEVERITY_TONE[item.severity]} className="shrink-0">
                {t(`adverseCategories.${item.category}`)}
              </Badge>
            </Row>
          ))}
          {legal.map((matter, index) => (
            <Row key={`l-${index}`}>
              <div className="flex min-w-0 gap-2">
                <Gavel className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden />
                <div className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-sm text-fg">{matter.summary}</span>
                  <span className="flex flex-wrap items-center gap-2 text-xs text-fg-muted">
                    {matter.date && (
                      <span className="font-mono">{formatPartialDate(matter.date, locale)}</span>
                    )}
                    {matter.status && <span>{matter.status}</span>}
                    <SourceRefs ids={matter.evidence.map((e) => e.source_id)} />
                  </span>
                </div>
              </div>
              <Badge
                tone={
                  matter.kind === "conviction" || matter.kind === "criminal_case"
                    ? "error"
                    : "warning"
                }
                className="shrink-0"
              >
                {t(`legalKinds.${matter.kind}`)}
              </Badge>
            </Row>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
