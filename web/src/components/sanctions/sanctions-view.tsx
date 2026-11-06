"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { RefreshCw, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { type FormEvent, useState } from "react";
import { MatchItem } from "@/components/portrait/sanctions-card";
import { Alert } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { NativeSelect } from "@/components/ui/native-select";
import { Skeleton } from "@/components/ui/skeleton";
import { listSanctions, searchSanctions, updateSanctions } from "@/lib/api/client";
import { type SanctionsListOut } from "@/lib/api/schemas";
import { errorMessage } from "@/lib/errors";
import { useSession } from "@/lib/session";

function ListStatus({ list }: { list: SanctionsListOut }) {
  const t = useTranslations("sanctions");
  if (list.status === "error")
    return (
      <Badge tone="error" title={list.error ?? undefined}>
        {t("error")}
      </Badge>
    );
  if (list.status === "never" || !list.fetched_at)
    return <Badge tone="neutral">{t("never")}</Badge>;
  if (list.stale) return <Badge tone="warning">{t("stale")}</Badge>;
  return <Badge tone="ok">{t("ok")}</Badge>;
}

export function SanctionsView() {
  const t = useTranslations();
  const format = useFormatter();
  const { me } = useSession();
  const lists = useQuery({ queryKey: ["sanctions-lists"], queryFn: listSanctions });
  const [name, setName] = useState("");
  const [birthDate, setBirthDate] = useState("");
  const [kind, setKind] = useState<"person" | "entity">("person");

  const search = useMutation({
    mutationFn: () => searchSanctions({ q: name.trim(), birthDate: birthDate || null, kind }),
  });
  const update = useMutation({ mutationFn: updateSanctions });

  function submit(event: FormEvent) {
    event.preventDefault();
    if (name.trim().length < 3) return;
    search.mutate();
  }

  const date = (value: string | null) =>
    value ? format.dateTime(new Date(value), { dateStyle: "medium" }) : t("common.dash");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div className="flex max-w-3xl flex-col gap-1">
          <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{t("sanctions.title")}</h1>
          <p className="text-sm text-fg-muted">{t("sanctions.subtitle")}</p>
        </div>
        {me?.user.role === "admin" && (
          <Button variant="secondary" disabled={update.isPending} onClick={() => update.mutate()}>
            <RefreshCw aria-hidden />
            {t("sanctions.update")}
          </Button>
        )}
      </div>
      {update.isSuccess && <Alert tone="info">{t("sanctions.updateQueued")}</Alert>}
      {update.isError && <Alert tone="error">{errorMessage(update.error, t)}</Alert>}

      {lists.isPending ? (
        <Skeleton className="h-48" />
      ) : lists.isError ? (
        <Alert tone="error">{errorMessage(lists.error, t)}</Alert>
      ) : (
        <div className="overflow-x-auto rounded-card border border-border">
          <table className="w-full min-w-[40rem] text-left text-sm">
            <thead className="border-b border-border bg-bg-subtle text-xs">
              <tr>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("sanctions.columns.list")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("sanctions.columns.published")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("sanctions.columns.fetched")}
                </th>
                <th scope="col" className="px-4 py-3 text-right font-medium">
                  {t("sanctions.columns.entries")}
                </th>
                <th scope="col" className="px-4 py-3 font-medium">
                  {t("sanctions.columns.status")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {lists.data.map((list) => (
                <tr key={list.id}>
                  <td className="px-4 py-3">
                    <a
                      href={list.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-medium text-fg hover:underline"
                    >
                      {list.name}
                    </a>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">{date(list.published_at)}</td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    {list.fetched_at
                      ? format.dateTime(new Date(list.fetched_at), {
                          dateStyle: "short",
                          timeStyle: "short",
                        })
                      : t("common.dash")}
                  </td>
                  <td className="px-4 py-3 text-right font-mono">{format.number(list.entries)}</td>
                  <td className="px-4 py-3">
                    <ListStatus list={list} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <section
        aria-labelledby="sanctions-search-title"
        className="flex flex-col gap-4 rounded-card-lg border border-border p-5 sm:p-6"
      >
        <h2 id="sanctions-search-title" className="text-lg font-semibold text-fg">
          {t("sanctions.searchTitle")}
        </h2>
        <form
          onSubmit={submit}
          className="grid gap-4 md:grid-cols-[minmax(0,1fr)_12rem_12rem_auto] md:items-end"
        >
          <Field id="sanctions-name" label={t("sanctions.name")}>
            <Input
              id="sanctions-name"
              value={name}
              minLength={3}
              maxLength={200}
              placeholder={t("sanctions.namePlaceholder")}
              onChange={(e) => setName(e.target.value)}
              required
            />
          </Field>
          <Field id="sanctions-dob" label={t("sanctions.birthDate")}>
            <Input
              id="sanctions-dob"
              type="date"
              value={birthDate}
              onChange={(e) => setBirthDate(e.target.value)}
            />
          </Field>
          <Field id="sanctions-kind" label={t("sanctions.kind")}>
            <NativeSelect
              id="sanctions-kind"
              value={kind}
              onChange={(e) => setKind(e.target.value as "person" | "entity")}
            >
              <option value="person">{t("sanctions.person")}</option>
              <option value="entity">{t("sanctions.entity")}</option>
            </NativeSelect>
          </Field>
          <Button type="submit" disabled={search.isPending || name.trim().length < 3}>
            <Search aria-hidden />
            {search.isPending ? t("sanctions.searching") : t("sanctions.submit")}
          </Button>
        </form>
        <p className="text-xs text-fg-muted">{t("sanctions.hint")}</p>
        {search.isError && <Alert tone="error">{errorMessage(search.error, t)}</Alert>}
        {search.isSuccess && (
          <div aria-live="polite">
            {search.data.matches.length === 0 ? (
              <Alert tone="info">{t("sanctions.noResults")}</Alert>
            ) : (
              <>
                <h3 className="text-sm font-semibold text-fg">
                  {t("sanctions.results")} ({search.data.matches.length})
                </h3>
                <ul className="mt-2 divide-y divide-border rounded-card border border-border">
                  {search.data.matches.map((match) => (
                    <li key={`${match.list_id}-${match.entry_ref}`} className="p-4">
                      <MatchItem match={match} />
                    </li>
                  ))}
                </ul>
              </>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
