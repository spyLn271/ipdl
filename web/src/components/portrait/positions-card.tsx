"use client";

import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { SourceRefs } from "@/components/portrait/source-refs";
import { type Position } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";
import { formatPeriod } from "@/lib/format";

const PUBLIC = new Set(["state_body", "public_function", "international_org"]);

export function PositionsCard({
  positions,
  basis,
}: {
  positions: readonly Position[];
  basis: readonly number[];
}) {
  const t = useTranslations();
  const locale = useLocale();
  const labels = {
    since: t("common.since"),
    until: t("common.until"),
    present: t("common.present"),
  };
  return (
    <SectionCard title={t("portrait.positionsTitle")} titleId="positions-title">
      {positions.length === 0 ? (
        <p className="text-sm text-fg-muted">{t("portrait.positionsEmpty")}</p>
      ) : (
        <ul>
          {positions.map((position, index) => (
            <Row key={`${position.title}-${index}`}>
              <div className="flex min-w-0 flex-col gap-0.5">
                <span className="text-sm font-medium text-fg">{position.title}</span>
                <span className="text-xs text-fg-muted">
                  {[
                    position.organization,
                    position.country && countryName(position.country, locale),
                    formatPeriod(position.start, position.end, locale, labels, position.is_current),
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </span>
                <SourceRefs ids={position.evidence.map((e) => e.source_id)} />
              </div>
              <Badge
                tone={
                  basis.includes(index)
                    ? "accent"
                    : PUBLIC.has(position.category)
                      ? "info"
                      : "neutral"
                }
                className="shrink-0"
              >
                {t(`positionCategories.${position.category}`)}
              </Badge>
            </Row>
          ))}
        </ul>
      )}
    </SectionCard>
  );
}
