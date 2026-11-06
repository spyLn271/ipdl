"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertCircle, Loader2, Plus, Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { useEffect, useState } from "react";
import { LevelBadge, PepBadge } from "@/components/registry/badges";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { Link } from "@/i18n/navigation";
import { listPersons } from "@/lib/api/client";
import {
  PEP_CATEGORIES,
  type PepCategory,
  type PersonSummary,
  type PortraitMeta,
  RISK_LEVELS,
  type RiskLevel,
} from "@/lib/api/schemas";
import { countryName } from "@/lib/countries";
import { errorMessage } from "@/lib/errors";
import { isBuilding } from "@/lib/format";
import { canEdit, useSession } from "@/lib/session";

const PAGE_SIZE = 20;

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

export function RegistryView() {
  const t = useTranslations();
  const { me } = useSession();
  const role = me?.user.role;
  const [q, setQ] = useState("");
  const [pep, setPep] = useState<PepCategory | null>(null);
  const [level, setLevel] = useState<RiskLevel | null>(null);
  const [page, setPage] = useState(1);
  const search = useDebounced(q, 300);

  const query = useQuery({
    queryKey: ["persons", { search, pep, level, page }],
    queryFn: () => listPersons({ q: search, pep, level, page, pageSize: PAGE_SIZE }),
    placeholderData: keepPreviousData,
    // Пока какой-то портрет строится — обновлять список
    refetchInterval: (state) =>
      state.state.data?.items.some((p) => isBuilding(p.latest?.status)) ? 4000 : false,
  });

  const filtered = Boolean(search.trim() || pep || level);
  const pages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-2xl flex-col gap-1">
          <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{t("registry.title")}</h1>
          <p className="text-sm text-fg-muted">
            {role === "partner" ? t("registry.partnerSubtitle") : t("registry.subtitle")}
          </p>
        </div>
        {canEdit(role) && (
          <Button asChild>
            <Link href="/persons/new">
              <Plus aria-hidden />
              {t("registry.newCheck")}
            </Link>
          </Button>
        )}
      </div>

      <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_auto_auto_auto] sm:items-end">
        <div className="relative">
          <label htmlFor="registry-search" className="sr-only">
            {t("registry.searchLabel")}
          </label>
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-fg-muted"
            aria-hidden
          />
          <Input
            id="registry-search"
            type="search"
            className="pl-9"
            placeholder={t("registry.searchPlaceholder")}
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </div>
        <NativeSelect
          aria-label={t("registry.filterPep")}
          value={pep ?? ""}
          onChange={(e) => {
            setPep((e.target.value || null) as PepCategory | null);
            setPage(1);
          }}
          className="sm:w-56"
        >
          <option value="">{t("registry.anyPep")}</option>
          {PEP_CATEGORIES.map((c) => (
            <option key={c} value={c}>
              {t(`pep.${c}`)}
            </option>
          ))}
        </NativeSelect>
        <NativeSelect
          aria-label={t("registry.filterLevel")}
          value={level ?? ""}
          onChange={(e) => {
            setLevel((e.target.value || null) as RiskLevel | null);
            setPage(1);
          }}
          className="sm:w-44"
        >
          <option value="">{t("registry.anyLevel")}</option>
          {RISK_LEVELS.filter((l) => l !== "no_data").map((l) => (
            <option key={l} value={l}>
              {t(`levels.${l}`)}
            </option>
          ))}
        </NativeSelect>
        <Button
          variant="ghost"
          onClick={() => {
            setQ("");
            setPep(null);
            setLevel(null);
            setPage(1);
          }}
          disabled={!filtered && !q}
        >
          {t("registry.reset")}
        </Button>
      </div>

      {query.isError ? (
        <Alert tone="error">{errorMessage(query.error, t)}</Alert>
      ) : query.isPending ? (
        <div className="flex flex-col gap-2" aria-busy>
          {Array.from({ length: 5 }, (_, i) => (
            <Skeleton key={i} className="h-16" />
          ))}
        </div>
      ) : query.data.items.length === 0 ? (
        <p className="rounded-card border border-dashed border-border p-10 text-center text-sm text-fg-muted">
          {filtered
            ? t("registry.emptyFiltered")
            : role === "partner"
              ? t("registry.emptyPartner")
              : t("registry.empty")}
        </p>
      ) : (
        <>
          <p className="text-sm text-fg-muted" aria-live="polite">
            {t("registry.total", { count: query.data.total })}
          </p>
          <RegistryTable items={query.data.items} />
          {pages > 1 && (
            <nav className="flex items-center justify-between gap-2" aria-label="pagination">
              <Button
                variant="secondary"
                size="sm"
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
              >
                {t("common.prev")}
              </Button>
              <span className="text-sm text-fg-muted">{t("common.pageOf", { page, pages })}</span>
              <Button
                variant="secondary"
                size="sm"
                disabled={page >= pages}
                onClick={() => setPage((p) => p + 1)}
              >
                {t("common.next")}
              </Button>
            </nav>
          )}
        </>
      )}
    </div>
  );
}

function BuildStatus({ latest }: { latest: PortraitMeta | null }) {
  const t = useTranslations();
  const format = useFormatter();
  if (!latest) return <span className="text-fg-muted">{t("registry.notBuilt")}</span>;
  if (isBuilding(latest.status)) {
    return (
      <span className="flex min-w-32 flex-col gap-1">
        <span className="flex items-center gap-1.5 text-xs text-fg">
          <Loader2 className="size-3.5 animate-spin" aria-hidden />
          {t(`jobStatus.${latest.status}`)} · {latest.progress}%
        </span>
        <span
          className="h-1.5 overflow-hidden rounded-badge bg-bg-subtle"
          role="progressbar"
          aria-valuenow={latest.progress}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label={t("portrait.progress.title")}
        >
          <span className="block h-full bg-accent" style={{ width: `${latest.progress}%` }} />
        </span>
      </span>
    );
  }
  if (latest.status === "failed") {
    return (
      <Badge tone="error">
        <AlertCircle className="size-3.5" aria-hidden />
        {t("jobStatus.failed")}
      </Badge>
    );
  }
  return (
    <span className="text-xs text-fg-muted">
      {t("registry.version", { version: latest.version })}
      {latest.finished_at &&
        ` · ${format.dateTime(new Date(latest.finished_at), { dateStyle: "short" })}`}
    </span>
  );
}

function RegistryTable({ items }: { items: PersonSummary[] }) {
  const t = useTranslations();
  const format = useFormatter();
  const locale = useLocale();
  return (
    <>
      <ul className="flex flex-col gap-2 md:hidden">
        {items.map((person) => (
          <li key={person.id}>
            <Link
              href={`/persons/${person.id}`}
              className="flex flex-col gap-2 rounded-card border border-border p-4 transition-colors hover:bg-bg-subtle"
            >
              <span className="flex items-start justify-between gap-3">
                <span className="min-w-0">
                  <span className="block font-medium text-fg">{person.full_name}</span>
                  {person.latin_name && (
                    <span className="block text-xs text-fg-muted">{person.latin_name}</span>
                  )}
                </span>
                {person.risk_score !== null && person.risk_level && (
                  <span className="flex shrink-0 items-center gap-2">
                    <span className="font-mono text-sm font-semibold">{person.risk_score}</span>
                    <LevelBadge level={person.risk_level} />
                  </span>
                )}
              </span>
              {person.pep_category && (
                <PepBadge category={person.pep_category} tenure={person.pep_tenure} />
              )}
              {person.position && (
                <span className="text-sm text-fg-muted">
                  {person.position}
                  {person.organization && `, ${person.organization}`}
                </span>
              )}
              <BuildStatus latest={person.latest} />
            </Link>
          </li>
        ))}
      </ul>
      <div className="hidden overflow-x-auto rounded-card border border-border md:block">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-border bg-bg-subtle text-xs text-fg">
            <tr>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.person")}
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.status")}
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.position")}
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.country")}
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.risk")}
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.build")}
              </th>
              <th scope="col" className="px-4 py-3 font-medium">
                {t("registry.columns.updated")}
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {items.map((person) => (
              <tr key={person.id} className="align-top transition-colors hover:bg-bg-subtle/60">
                <td className="px-4 py-3">
                  <Link
                    href={`/persons/${person.id}`}
                    className="font-medium text-fg underline-offset-4 hover:underline"
                  >
                    {person.full_name}
                  </Link>
                  {person.latin_name && (
                    <span className="block text-xs text-fg-muted">{person.latin_name}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  {person.pep_category ? (
                    <PepBadge category={person.pep_category} tenure={person.pep_tenure} />
                  ) : (
                    <span className="text-fg-muted">{t("common.dash")}</span>
                  )}
                </td>
                <td className="max-w-72 px-4 py-3 text-fg">
                  {person.position ?? <span className="text-fg-muted">{t("common.dash")}</span>}
                  {person.organization && (
                    <span className="block text-xs text-fg-muted">{person.organization}</span>
                  )}
                </td>
                <td className="px-4 py-3 whitespace-nowrap">
                  {person.country ? countryName(person.country, locale) : t("common.dash")}
                </td>
                <td className="px-4 py-3">
                  {person.risk_score !== null && person.risk_level ? (
                    <span className="flex items-center gap-2">
                      <span className="font-mono font-semibold text-fg">{person.risk_score}</span>
                      <LevelBadge level={person.risk_level} />
                    </span>
                  ) : (
                    <span className="text-fg-muted">{t("common.dash")}</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <BuildStatus latest={person.latest} />
                </td>
                <td className="px-4 py-3 whitespace-nowrap text-fg-muted">
                  {format.dateTime(new Date(person.updated_at), { dateStyle: "medium" })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
