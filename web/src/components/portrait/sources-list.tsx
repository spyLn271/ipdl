"use client";

import { ChevronDown, ExternalLink } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { useMemo, useState } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/portrait/section-card";
import { type Portrait, type Source } from "@/lib/api/schemas";
import { evidenceBySource } from "@/lib/portrait";

const VERIFICATION_TONE = { unverified: "neutral", confirmed: "ok", disputed: "error" } as const;
const INITIAL = 8;

function SourceItem({ source, quotes }: { source: Source; quotes: readonly string[] }) {
  const t = useTranslations();
  const format = useFormatter();
  return (
    <li
      id={`source-${source.id}`}
      className="flex scroll-mt-20 flex-col gap-1.5 border-t border-border py-3 first:border-t-0 first:pt-0 target:rounded-card target:bg-accent-subtle/40"
    >
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="flex min-w-0 items-start gap-2">
          <span className="mt-0.5 rounded-[4px] bg-bg-subtle px-1.5 py-0.5 font-mono text-[11px] text-fg">
            {source.id}
          </span>
          <a
            href={source.url}
            target="_blank"
            rel="noopener noreferrer"
            className="min-w-0 text-sm font-medium break-words text-fg underline-offset-4 hover:underline"
            aria-label={`${source.title} — ${t("portrait.openSource", { id: source.id })}`}
          >
            {source.title}
            <ExternalLink className="ml-1 inline size-3 text-fg-muted" aria-hidden />
          </a>
        </div>
        <span className="flex shrink-0 flex-wrap gap-1">
          <Badge tone="outline">{t(`sourceKinds.${source.kind}`)}</Badge>
          <Badge tone={VERIFICATION_TONE[source.verification]}>
            {t(`verifications.${source.verification}`)}
          </Badge>
        </span>
      </div>
      <p className="text-xs text-fg-muted">
        {source.domain}
        {source.published &&
          ` · ${format.dateTime(new Date(source.published), { dateStyle: "medium" })}`}
        {source.analyzed && ` · ${t("portrait.analyzed")}`}
        {source.analyzed && ` · ${t("portrait.sourceFacts", { count: source.facts })}`}
      </p>
      {quotes.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {quotes.slice(0, 4).map((quote) => (
            <li key={quote}>
              <blockquote className="border-l-2 border-accent/50 pl-2 text-xs text-fg">
                «{quote}»
              </blockquote>
            </li>
          ))}
        </ul>
      ) : (
        source.snippet && <p className="line-clamp-2 text-xs text-fg-muted">{source.snippet}</p>
      )}
    </li>
  );
}

export function SourcesList({ portrait }: { portrait: Portrait }) {
  const t = useTranslations("portrait");
  const [expanded, setExpanded] = useState(false);
  const quotes = useMemo(() => evidenceBySource(portrait), [portrait]);
  // Сначала источники, давшие факты, затем проанализированные, затем остальные
  const ordered = useMemo(
    () =>
      [...portrait.sources].sort(
        (a, b) =>
          Number(b.facts > 0) - Number(a.facts > 0) ||
          Number(b.analyzed) - Number(a.analyzed) ||
          b.relevance - a.relevance,
      ),
    [portrait.sources],
  );
  const shown = expanded ? ordered : ordered.slice(0, INITIAL);
  return (
    <SectionCard
      id="sources-list"
      className="scroll-mt-20"
      title={t("allSources", { count: ordered.length })}
      titleId="sources-list-title"
    >
      <ul>
        {shown.map((source) => (
          <SourceItem key={source.id} source={source} quotes={quotes.get(source.id) ?? []} />
        ))}
      </ul>
      {ordered.length > INITIAL && (
        <Button
          variant="ghost"
          size="sm"
          className="mt-2"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
        >
          <ChevronDown
            className={expanded ? "rotate-180 transition-transform" : "transition-transform"}
            aria-hidden
          />
          {expanded ? t("showLess") : t("showAll", { count: ordered.length })}
        </Button>
      )}
    </SectionCard>
  );
}
