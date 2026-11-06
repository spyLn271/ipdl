"use client";

import { useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { type ExchangeRequest, type Portrait } from "@/lib/api/schemas";
import { groupTone, sourceGroups } from "@/lib/portrait";

/** «Источники и верификация» из макета: реестры, СМИ, санкции, обмен с ПФР. */
export function VerificationCard({
  portrait,
  requests,
}: {
  portrait: Portrait;
  requests: readonly ExchangeRequest[];
}) {
  const t = useTranslations("portrait");
  const groups = sourceGroups(portrait, requests);
  return (
    <SectionCard
      title={t("sourcesTitle")}
      titleId="verification-title"
      aside={
        <a href="#sources-list" className="shrink-0 text-xs text-accent hover:underline">
          {t("allSources", { count: portrait.sources.length })}
        </a>
      }
    >
      <ul>
        {groups.map((group) => (
          <Row key={group.key} className="items-center">
            <span className="text-sm text-fg">
              {t(`groups.${group.key}`)}
              {group.count > 0 && (
                <span className="ml-1 text-xs text-fg-muted">({group.count})</span>
              )}
            </span>
            <Badge tone={groupTone(group.status)} className="shrink-0">
              {t(`groupStatus.${group.status}`)}
            </Badge>
          </Row>
        ))}
      </ul>
    </SectionCard>
  );
}
