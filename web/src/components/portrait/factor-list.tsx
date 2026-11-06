"use client";

import { UserCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { LevelBadge } from "@/components/registry/badges";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { SourceRefs } from "@/components/portrait/source-refs";
import { type Factor } from "@/lib/api/schemas";

/** Восемь факторов риска из методики — как в макете: название, комментарий, уровень. */
export function FactorList({ factors }: { factors: readonly Factor[] }) {
  const t = useTranslations();
  return (
    <SectionCard title={t("portrait.factorsTitle")} titleId="factors-title">
      <ul>
        {factors.map((factor) => (
          <Row key={factor.key} data-factor={factor.key}>
            <div className="flex min-w-0 flex-col gap-1">
              <span className="text-sm font-medium text-fg">{t(`factors.${factor.key}`)}</span>
              <span className="text-xs text-fg-muted">{factor.comment}</span>
              {(factor.evidence.length > 0 || factor.overridden) && (
                <span className="flex flex-wrap items-center gap-2">
                  {factor.overridden && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-info-fg">
                      <UserCheck className="size-3.5" aria-hidden />
                      {t("portrait.overridden")} ·{" "}
                      {t("portrait.autoLevel", { level: t(`levels.${factor.auto_level}`) })}
                    </span>
                  )}
                  <SourceRefs ids={factor.evidence} />
                </span>
              )}
            </div>
            <LevelBadge level={factor.level} className="shrink-0" />
          </Row>
        ))}
      </ul>
    </SectionCard>
  );
}
