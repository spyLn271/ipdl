"use client";

import { useLocale, useTranslations } from "next-intl";
import { type ReactNode } from "react";
import { PepBadge } from "@/components/registry/badges";
import { SourceRefs } from "@/components/portrait/source-refs";
import { type Portrait } from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";
import { formatPartialDate, formatPeriod, initials } from "@/lib/format";
import { mainPosition } from "@/lib/portrait";

function Item({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-fg-muted">{label}</dt>
      <dd className="text-sm font-medium text-fg">{children}</dd>
    </div>
  );
}

export function IdentityCard({ portrait }: { portrait: Portrait }) {
  const t = useTranslations();
  const locale = useLocale();
  const { identity, pep } = portrait;
  const position = mainPosition(portrait);
  const dash = t("common.dash");
  const birth = identity.birth_date ? formatPartialDate(identity.birth_date.value, locale) : "";
  const place = identity.birth_place?.value ?? "";
  const periodLabels = {
    since: t("common.since"),
    until: t("common.until"),
    present: t("common.present"),
  };
  const conflicts = Object.values(identity.conflicts).filter((v) => v.length > 1);

  return (
    <section
      aria-labelledby="identity-title"
      className="rounded-card-lg border border-border bg-bg p-5"
    >
      <h2 id="identity-title" className="sr-only">
        {t("portrait.identity.title")}
      </h2>
      <div className="flex items-start gap-4">
        <div
          className="flex h-[7.5rem] w-24 shrink-0 items-center justify-center rounded-card bg-bg-subtle font-mono text-2xl font-semibold text-fg-muted"
          title={t("portrait.identity.photo")}
          aria-hidden
        >
          {initials(identity.full_name)}
        </div>
        <div className="flex min-w-0 flex-col gap-1">
          <p className="text-xl leading-tight font-semibold text-fg">{identity.full_name}</p>
          {identity.latin_name && <p className="text-sm text-fg-muted">{identity.latin_name}</p>}
          <PepBadge category={pep.category} tenure={pep.tenure} className="mt-2 w-fit" />
        </div>
      </div>
      <dl className="mt-5 flex flex-col gap-3.5">
        <Item label={t("portrait.identity.birth")}>
          {[birth, place].filter(Boolean).join(", ") || dash}
          {identity.birth_date && (
            <SourceRefs
              className="ml-1.5"
              ids={identity.birth_date.evidence.map((e) => e.source_id)}
            />
          )}
        </Item>
        {conflicts.map((values) => (
          <p key={values.join("|")} className="-mt-2 text-xs text-warning-fg">
            {t("portrait.identity.conflict", { values: values.join(" / ") })}
          </p>
        ))}
        <Item label={t("portrait.identity.citizenship")}>
          {identity.citizenship.length > 0
            ? identity.citizenship.map((c) => countryName(c, locale)).join(", ")
            : dash}
        </Item>
        <Item label={t("portrait.identity.position")}>{position?.title ?? dash}</Item>
        <Item label={t("portrait.identity.organization")}>
          {position?.organization ?? dash}
          {position?.country && (
            <span className="font-normal text-fg-muted">
              {" "}
              · {countryName(position.country, locale)}
            </span>
          )}
        </Item>
        <Item label={t("portrait.identity.period")}>
          {(position &&
            formatPeriod(
              position.start,
              position.end,
              locale,
              periodLabels,
              position.is_current,
            )) ||
            dash}
        </Item>
      </dl>
    </section>
  );
}
