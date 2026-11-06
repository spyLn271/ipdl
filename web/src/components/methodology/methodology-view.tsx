"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { type ReactNode } from "react";
import { z } from "zod";
import { LevelBadge } from "@/components/registry/badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { getMethodology } from "@/lib/api/client";
import { FACTOR_KEYS, type FactorKey, type RiskLevel } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";
import { errorMessage } from "@/lib/errors";

// Правовая основа приходит из methodology/risk-model.yaml — проверяем только то, что показываем
const legalBasisSchema = z.object({
  pep_definition: z
    .object({
      act: z.string(),
      clause: z.string(),
      url: z.string().optional(),
      foreign_state_body: z.string().optional(),
      foreign_public_function: z.string().optional(),
      international_org: z.string().optional(),
      domestic: z.string().optional(),
    })
    .optional(),
  pep_measures: z.object({ clause: z.string(), measures: z.array(z.string()) }).optional(),
  domestic_list: z.object({ clause: z.string(), note: z.string() }).optional(),
  fatf: z.object({ clause: z.string(), url: z.string().optional() }).optional(),
});

const LEVELS: RiskLevel[] = ["low", "medium", "high"];

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle id={id}>{title}</CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-3 pt-3 text-sm">{children}</CardContent>
    </Card>
  );
}

function SourceLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 text-accent hover:underline"
    >
      {children}
      <ExternalLink className="size-3" aria-hidden />
    </a>
  );
}

export function MethodologyView() {
  const t = useTranslations();
  const format = useFormatter();
  const locale = useLocale();
  const query = useQuery({
    queryKey: ["methodology"],
    queryFn: getMethodology,
    staleTime: Infinity,
  });

  if (query.isPending) return <Skeleton className="h-96" />;
  if (query.isError) return <Alert tone="error">{errorMessage(query.error, t)}</Alert>;

  const { risk_model: model, jurisdictions, sanctions_sources: lists } = query.data;
  const legal = legalBasisSchema.safeParse(model.legal_basis).data;
  const date = (value: string) => format.dateTime(new Date(value), { dateStyle: "long" });
  const factorKeys = FACTOR_KEYS.filter((key) => key in model.factors);

  return (
    <div className="flex flex-col gap-6">
      <div className="flex max-w-3xl flex-col gap-1">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{t("methodology.title")}</h1>
        <p className="text-sm text-fg-muted">{t("methodology.subtitle")}</p>
        <p className="mt-2 w-fit rounded-badge bg-bg-subtle px-3 py-1 font-mono text-xs text-fg">
          {model.id} · {model.title}
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
        <Section id="m-factors" title={t("methodology.factorsTitle")}>
          <ul className="flex flex-col">
            {factorKeys.map((key: FactorKey) => {
              const weight = model.factors[key]?.weight ?? 0;
              return (
                <li
                  key={key}
                  className="flex items-center gap-3 border-t border-border py-2.5 first:border-t-0 first:pt-0"
                >
                  <span className="min-w-0 flex-1 text-fg">{t(`factors.${key}`)}</span>
                  <span
                    className="h-1.5 w-24 overflow-hidden rounded-badge bg-bg-subtle"
                    aria-hidden
                  >
                    <span
                      className="block h-full bg-accent"
                      style={{ width: `${Math.round(weight * 400)}%` }}
                    />
                  </span>
                  <span className="w-12 text-right font-mono text-xs text-fg">
                    {format.number(weight, { style: "percent" })}
                  </span>
                </li>
              );
            })}
          </ul>
          <p className="text-xs text-fg-muted">{t("methodology.formula")}</p>
        </Section>

        <div className="flex flex-col gap-5">
          <Section id="m-bands" title={t("methodology.bandsTitle")}>
            <ul className="flex flex-col gap-2">
              {LEVELS.map((level) => {
                const band = model.bands[level];
                return (
                  <li key={level} className="flex flex-wrap items-center justify-between gap-2">
                    <LevelBadge level={level} />
                    <span className="font-mono text-xs text-fg">
                      {band ? `${band[0]}–${band[1]}` : ""}
                    </span>
                    <span className="text-xs text-fg-muted">
                      {t("methodology.reviewMonths", { months: model.review_months[level] ?? 0 })}
                    </span>
                  </li>
                );
              })}
            </ul>
            <h3 className="mt-2 text-xs font-medium text-fg">{t("methodology.pointsTitle")}</h3>
            <p className="flex flex-wrap gap-2">
              {LEVELS.map((level) => (
                <Badge key={level} tone="outline">
                  {t(`levels.${level}`)}: {model.points[level]}
                </Badge>
              ))}
            </p>
            <p className="text-xs text-fg-muted">
              {t("methodology.noDataPoints", { points: model.no_data_points })}
            </p>
          </Section>
          <Section id="m-floors" title={t("methodology.floorsTitle")}>
            <ul className="flex flex-col gap-2">
              {Object.entries(model.floors).map(([name, floor]) => (
                <li key={name} className="flex items-start gap-3">
                  <Badge tone="warning" className="shrink-0">
                    {t("methodology.floorScore", { score: floor.min_score })}
                  </Badge>
                  <span className="text-xs text-fg">{floor.reason}</span>
                </li>
              ))}
            </ul>
          </Section>
        </div>
      </div>

      {legal && (
        <Section id="m-legal" title={t("methodology.legalTitle")}>
          {legal.pep_definition && (
            <div className="flex flex-col gap-2">
              <h3 className="font-medium text-fg">
                {t("methodology.pepDefinition")} — {legal.pep_definition.clause}
              </h3>
              <p className="text-xs text-fg-muted">
                {legal.pep_definition.act}
                {legal.pep_definition.url && (
                  <>
                    {" · "}
                    <SourceLink href={legal.pep_definition.url}>adilet.zan.kz</SourceLink>
                  </>
                )}
              </p>
              <ul className="flex flex-col gap-2">
                {[
                  legal.pep_definition.foreign_state_body,
                  legal.pep_definition.foreign_public_function,
                  legal.pep_definition.international_org,
                  legal.pep_definition.domestic,
                ]
                  .filter((text): text is string => Boolean(text))
                  .map((text) => (
                    <li key={text}>
                      <blockquote className="border-l-2 border-accent/50 pl-3 text-sm text-fg">
                        {text}
                      </blockquote>
                    </li>
                  ))}
              </ul>
            </div>
          )}
          {legal.pep_measures && (
            <div className="flex flex-col gap-1.5">
              <h3 className="font-medium text-fg">
                {t("methodology.measures")} — {legal.pep_measures.clause}
              </h3>
              <ol className="flex list-decimal flex-col gap-1 pl-5 text-fg">
                {legal.pep_measures.measures.map((m) => (
                  <li key={m}>{m}</li>
                ))}
              </ol>
            </div>
          )}
          {legal.domestic_list && (
            <div className="flex flex-col gap-1">
              <h3 className="font-medium text-fg">
                {t("methodology.domesticList")} — {legal.domestic_list.clause}
              </h3>
              <p className="text-fg-muted">{legal.domestic_list.note}</p>
            </div>
          )}
          {legal.fatf && (
            <p className="text-fg-muted">
              {legal.fatf.url ? (
                <SourceLink href={legal.fatf.url}>{legal.fatf.clause}</SourceLink>
              ) : (
                legal.fatf.clause
              )}
            </p>
          )}
        </Section>
      )}

      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
        <Section id="m-fatf" title={t("methodology.fatfTitle")}>
          <p className="text-xs text-fg-muted">
            {t("methodology.asOf", { date: date(jurisdictions.fatf.as_of) })} ·{" "}
            <SourceLink href={jurisdictions.fatf.source_url}>{t("methodology.source")}</SourceLink>
          </p>
          <h3 className="font-medium text-fg">{t("methodology.callForAction")}</h3>
          <ul className="flex flex-wrap gap-2">
            {Object.entries(jurisdictions.fatf.call_for_action).map(([code, measure]) => (
              <li key={code}>
                <Badge tone="error" title={measure}>
                  {countryName(code, locale)} · {measure}
                </Badge>
              </li>
            ))}
          </ul>
          <h3 className="font-medium text-fg">
            {t("methodology.increasedMonitoring")} ({jurisdictions.fatf.increased_monitoring.length}
            )
          </h3>
          <ul className="flex flex-wrap gap-1.5">
            {jurisdictions.fatf.increased_monitoring.map((code) => (
              <li key={code}>
                <Badge tone="warning">{countryName(code, locale)}</Badge>
              </li>
            ))}
          </ul>
          <p className="text-xs text-fg-muted">{jurisdictions.fatf.source}</p>
        </Section>
        <Section id="m-offshore" title={t("methodology.preferentialTitle")}>
          <p className="text-xs text-fg-muted">
            {t("methodology.asOf", { date: date(jurisdictions.preferential_tax.as_of) })} ·{" "}
            <SourceLink href={jurisdictions.preferential_tax.source_url}>
              {t("methodology.source")}
            </SourceLink>
          </p>
          <p className="text-xs text-fg">{jurisdictions.preferential_tax.source}</p>
          <ul className="flex flex-wrap gap-1.5">
            {jurisdictions.preferential_tax.codes.map((code) => (
              <li key={code}>
                <Badge tone="neutral">{countryName(code, locale)}</Badge>
              </li>
            ))}
          </ul>
          {Object.keys(jurisdictions.preferential_tax.partial).length > 0 && (
            <>
              <h3 className="font-medium text-fg">{t("methodology.partial")}</h3>
              <ul className="flex flex-col gap-1 text-xs text-fg">
                {Object.entries(jurisdictions.preferential_tax.partial).map(([code, note]) => (
                  <li key={code}>
                    {countryName(code, locale)} — {note}
                  </li>
                ))}
              </ul>
            </>
          )}
        </Section>
      </div>

      <Section id="m-sanctions" title={t("methodology.sanctionsTitle")}>
        <ul className="flex flex-col">
          {lists.map((list) => (
            <li
              key={list.id}
              className="flex flex-wrap items-baseline justify-between gap-2 border-t border-border py-2.5 first:border-t-0 first:pt-0"
            >
              <span className="text-fg">{list.name}</span>
              <SourceLink href={list.url}>{list.short}</SourceLink>
            </li>
          ))}
        </ul>
      </Section>
    </div>
  );
}
