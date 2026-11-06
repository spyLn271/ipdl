"use client";

import { ExternalLink, ShieldAlert, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Row, SectionCard } from "@/components/portrait/section-card";
import { type SanctionsMatch, type Portrait } from "@/lib/api/schemas";

export function MatchItem({ match }: { match: SanctionsMatch }) {
  const t = useTranslations("portrait");
  const dob =
    match.dob_match === true ? "match" : match.dob_match === false ? "mismatch" : "unknown";
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <span className="text-sm font-medium text-fg">
        {match.primary_name}{" "}
        <span className="font-mono text-xs font-normal text-fg-muted">{match.entry_ref}</span>
      </span>
      <span className="text-xs text-fg-muted">
        {match.list_name} · {t("score", { score: Math.round(match.score) })} ·{" "}
        <span
          className={
            dob === "match" ? "text-error-fg" : dob === "mismatch" ? "text-ok-fg" : undefined
          }
        >
          {t(`dob.${dob}`)}
        </span>
      </span>
      {match.programs.length > 0 && (
        <span className="text-xs text-fg-muted">
          {t("programs", { programs: match.programs.slice(0, 3).join(", ") })}
        </span>
      )}
      {match.url && (
        <a
          href={match.url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex w-fit items-center gap-1 text-xs text-accent hover:underline"
        >
          <ExternalLink className="size-3" aria-hidden />
          {match.list_name}
        </a>
      )}
    </div>
  );
}

export function SanctionsCard({ portrait }: { portrait: Portrait }) {
  const t = useTranslations("portrait");
  const format = useFormatter();
  const { lists, matches } = portrait.sanctions;
  return (
    <SectionCard
      title={t("sanctionsTitle")}
      titleId="sanctions-title"
      aside={
        lists.length > 0 &&
        (matches.length > 0 ? (
          <ShieldAlert className="size-5 text-error" aria-hidden />
        ) : (
          <ShieldCheck className="size-5 text-ok" aria-hidden />
        ))
      }
    >
      {lists.length === 0 ? (
        <Alert tone="warning">{t("notChecked")}</Alert>
      ) : (
        <>
          <h3 className="text-xs font-medium text-fg-muted">{t("listsChecked")}</h3>
          <ul className="mt-2 flex flex-col gap-1.5">
            {lists.map((list) => (
              <li key={list.id} className="flex items-baseline justify-between gap-2 text-sm">
                <span className="min-w-0 text-fg">{list.name}</span>
                {list.published_at && (
                  <span className="shrink-0 text-xs whitespace-nowrap text-fg-muted">
                    {t("listDate", {
                      date: format.dateTime(new Date(list.published_at), { dateStyle: "short" }),
                    })}
                  </span>
                )}
              </li>
            ))}
          </ul>
          {matches.length === 0 ? (
            <p className="mt-3 flex items-center gap-2 text-sm text-ok-fg">
              <Badge tone="ok">{t("noMatches")}</Badge>
            </p>
          ) : (
            <div className="mt-4">
              <h3 className="text-xs font-semibold text-error-fg">{t("matchesTitle")}</h3>
              <ul className="mt-2">
                {matches.map((match) => (
                  <Row key={`${match.list_id}-${match.entry_ref}`}>
                    <MatchItem match={match} />
                  </Row>
                ))}
              </ul>
            </div>
          )}
        </>
      )}
    </SectionCard>
  );
}
