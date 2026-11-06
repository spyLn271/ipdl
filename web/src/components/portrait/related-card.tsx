"use client";

import { Building2, ShieldAlert, UserRound } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { Badge } from "@/components/ui/badge";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { SourceRefs } from "@/components/portrait/source-refs";
import { type Portrait } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";

export function RelatedCard({ portrait }: { portrait: Portrait }) {
  const t = useTranslations();
  const locale = useLocale();
  const { relations, companies } = portrait;
  const related = portrait.sanctions.related;
  return (
    <SectionCard title={t("portrait.relatedTitle")} titleId="related-title">
      {relations.length === 0 && companies.length === 0 ? (
        <p className="text-sm text-fg-muted">{t("portrait.relatedEmpty")}</p>
      ) : (
        <ul>
          {relations.map((relation) => {
            const hit = related.find((m) => m.query === relation.name);
            return (
              <Row key={`r-${relation.name}`} className="justify-start gap-2">
                <UserRound className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden />
                <div className="flex min-w-0 flex-col gap-1">
                  <span className="text-sm font-medium text-fg">{relation.name}</span>
                  <span className="text-xs text-fg-muted">
                    {t(`relationKinds.${relation.relation}`)}
                    {relation.note && ` · ${relation.note}`}
                  </span>
                  {(relation.is_public_official || hit) && (
                    <span className="flex flex-wrap gap-1">
                      {relation.is_public_official && (
                        <Badge tone="accent">{t("portrait.publicOfficial")}</Badge>
                      )}
                      {hit && (
                        <Badge tone="error" title={`${hit.list_name}: ${hit.primary_name}`}>
                          <ShieldAlert className="size-3.5" aria-hidden />
                          {t("factors.sanctions")}
                        </Badge>
                      )}
                    </span>
                  )}
                  <SourceRefs ids={relation.evidence.map((e) => e.source_id)} />
                </div>
              </Row>
            );
          })}
          {companies.map((company) => {
            const hit = related.find((m) => m.query === company.name);
            return (
              <Row key={`c-${company.name}`}>
                <div className="flex min-w-0 gap-2">
                  <Building2 className="mt-0.5 size-4 shrink-0 text-fg-muted" aria-hidden />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-sm font-medium text-fg">{company.name}</span>
                    <span className="text-xs text-fg-muted">
                      {t(`companyRoles.${company.role}`)}
                      {company.share_percent !== null &&
                        ` · ${t("portrait.share", { share: company.share_percent })}`}
                      {company.country && ` · ${countryName(company.country, locale)}`}
                    </span>
                    <SourceRefs ids={company.evidence.map((e) => e.source_id)} />
                  </div>
                </div>
                {hit && (
                  <Badge
                    tone="error"
                    className="shrink-0"
                    title={`${hit.list_name}: ${hit.primary_name}`}
                  >
                    <ShieldAlert className="size-3.5" aria-hidden />
                    {t("factors.sanctions")}
                  </Badge>
                )}
              </Row>
            );
          })}
        </ul>
      )}
    </SectionCard>
  );
}
