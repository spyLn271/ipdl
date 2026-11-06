"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  ClipboardCheck,
  FileDown,
  FileText,
  History,
  MessageSquarePlus,
  RefreshCw,
  Send,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { useEffect, useState } from "react";
import { ErrorState } from "@/components/layout/error-state";
import { AdverseCard } from "@/components/portrait/adverse-card";
import { ConclusionCard } from "@/components/portrait/conclusion-card";
import { FactorList } from "@/components/portrait/factor-list";
import { IdentityCard } from "@/components/portrait/identity-card";
import { PepCard } from "@/components/portrait/pep-card";
import { PositionsCard } from "@/components/portrait/positions-card";
import { ProgressCard } from "@/components/portrait/progress-card";
import { RelatedCard } from "@/components/portrait/related-card";
import { RequestDialog } from "@/components/portrait/request-dialog";
import { RequestLogCard } from "@/components/portrait/request-log-card";
import { ReviewDialog } from "@/components/portrait/review-dialog";
import { RiskScoreCard } from "@/components/portrait/risk-score-card";
import { SanctionsCard } from "@/components/portrait/sanctions-card";
import { SourcesList } from "@/components/portrait/sources-list";
import { TimelineCard } from "@/components/portrait/timeline-card";
import { VerificationCard } from "@/components/portrait/verification-card";
import { LevelBadge } from "@/components/registry/badges";
import { Alert } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Skeleton } from "@/components/ui/skeleton";
import { Link } from "@/i18n/navigation";
import {
  type ExportFormat,
  exportPortrait,
  getPerson,
  getPortrait,
  makeCurrent,
  rebuildPortrait,
} from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import {
  type ExchangeRequest,
  type PersonDetail,
  type PortraitMeta,
  type PortraitOut,
  type RequestKind,
} from "@/lib/api/schemas";
import { downloadBlob } from "@/lib/download";
import { errorMessage } from "@/lib/errors";
import { isBuilding, isFinal } from "@/lib/format";
import { pollInterval } from "@/lib/polling";
import { useSession } from "@/lib/session";

export function PortraitView({ personId }: { personId: string }) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const { me } = useSession();
  const [selected, setSelected] = useState<string | null>(null);

  const detail = useQuery({ queryKey: ["person", personId], queryFn: () => getPerson(personId) });
  const latest = detail.data?.versions[0] ?? null;
  const building = isBuilding(latest?.status);

  const live = useQuery({
    queryKey: ["portrait", latest?.id],
    queryFn: () => getPortrait(latest!.id),
    enabled: building && Boolean(latest),
    refetchInterval: (query) => pollInterval(query.state.data, query.state.error),
    staleTime: 0,
  });
  const liveStatus = live.data?.meta.status;
  useEffect(() => {
    // Версия достроилась — обновить карточку и реестр
    if (building && isFinal(liveStatus)) {
      void queryClient.invalidateQueries({ queryKey: ["person", personId] });
      void queryClient.invalidateQueries({ queryKey: ["persons"] });
    }
  }, [building, liveStatus, personId, queryClient]);

  const currentId = detail.data?.current?.meta.id ?? null;
  const viewingOther = selected !== null && selected !== currentId;
  const other = useQuery({
    queryKey: ["portrait", selected],
    queryFn: () => getPortrait(selected!),
    enabled: viewingOther,
  });

  if (detail.isPending) {
    return (
      <div className="flex flex-col gap-4" aria-busy>
        <Skeleton className="h-10 w-2/3" />
        <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)_320px]">
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
          <Skeleton className="h-96" />
        </div>
      </div>
    );
  }
  if (detail.isError) {
    const notFound = detail.error instanceof ApiError && detail.error.status === 404;
    return (
      <ErrorState
        title={notFound ? t("errors.notFoundTitle") : t("errors.loadFailed")}
        text={errorMessage(detail.error, t)}
        onRetry={notFound ? undefined : () => void detail.refetch()}
      />
    );
  }

  const data = detail.data;
  const shown: PortraitOut | null = viewingOther ? (other.data ?? null) : data.current;
  const liveMeta = live.data?.meta ?? latest;
  const failedLatest = latest?.status === "failed" ? latest : null;

  return (
    <div className="flex flex-col gap-5">
      <Toolbar
        detail={data}
        shown={shown}
        building={building}
        onSelectVersion={setSelected}
        partnerId={me?.user.role === "partner" ? (me.user.partner?.id ?? null) : null}
      />

      {building && liveMeta && <ProgressCard meta={liveMeta} />}
      {failedLatest && (
        <FailedNotice meta={failedLatest} personId={personId} canEdit={data.can_edit} />
      )}
      {!data.current && !building && !failedLatest && (
        <p className="rounded-card border border-dashed border-border p-10 text-center text-sm text-fg-muted">
          {t("portrait.progress.notBuilt")}
        </p>
      )}
      {viewingOther && shown && data.current && (
        <Alert tone="info">
          {t("portrait.viewingVersion", {
            version: shown.meta.version,
            current: data.current.meta.version,
          })}{" "}
          <button
            type="button"
            className="font-medium text-accent underline"
            onClick={() => setSelected(null)}
          >
            {t("portrait.showCurrent")}
          </button>
        </Alert>
      )}
      {viewingOther && other.isPending && <Skeleton className="h-96" />}
      {shown?.portrait && (
        <PortraitBody
          out={shown}
          personId={personId}
          requests={data.requests}
          canEdit={data.can_edit}
        />
      )}
    </div>
  );
}

function FailedNotice({
  meta,
  personId,
  canEdit,
}: {
  meta: PortraitMeta;
  personId: string;
  canEdit: boolean;
}) {
  const t = useTranslations();
  const queryClient = useQueryClient();
  const retry = useMutation({
    mutationFn: () => rebuildPortrait(personId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["person", personId] }),
  });
  return (
    <Alert tone="error">
      <p className="font-medium">
        {t("portrait.progress.failedTitle")} · {t("portrait.version", { version: meta.version })}
      </p>
      {meta.error && <p className="mt-1">{meta.error}</p>}
      {canEdit && (
        <Button
          size="sm"
          variant="secondary"
          className="mt-3"
          disabled={retry.isPending}
          onClick={() => retry.mutate()}
        >
          <RefreshCw aria-hidden />
          {t("portrait.progress.retry")}
        </Button>
      )}
      {retry.isError && <p className="mt-2">{errorMessage(retry.error, t)}</p>}
    </Alert>
  );
}

interface ToolbarProps {
  detail: PersonDetail;
  shown: PortraitOut | null;
  building: boolean;
  partnerId: string | null;
  onSelectVersion: (id: string | null) => void;
}

function Toolbar({ detail, shown, building, partnerId, onSelectVersion }: ToolbarProps) {
  const t = useTranslations();
  const format = useFormatter();
  const queryClient = useQueryClient();
  const { person, can_edit: canEdit } = detail;
  const [dialog, setDialog] = useState<RequestKind | "review" | null>(null);
  const [exportError, setExportError] = useState<unknown>(null);
  const done = shown?.meta.status === "done" && shown.portrait !== null;
  const isCurrent = shown?.meta.id === detail.current?.meta.id;

  const rebuild = useMutation({
    mutationFn: () => rebuildPortrait(person.id),
    onSuccess: () => {
      onSelectVersion(null);
      void queryClient.invalidateQueries({ queryKey: ["person", person.id] });
    },
  });
  const exporter = useMutation({
    mutationFn: (fmt: ExportFormat) => exportPortrait(shown!.meta.id, fmt),
    onMutate: () => setExportError(null),
    onSuccess: ({ blob, filename }) => downloadBlob(blob, filename),
    onError: (error) => setExportError(error),
  });
  const current = useMutation({
    mutationFn: (id: string) => makeCurrent(id),
    onSuccess: () => {
      onSelectVersion(null);
      void queryClient.invalidateQueries({ queryKey: ["person", person.id] });
      void queryClient.invalidateQueries({ queryKey: ["persons"] });
    },
  });

  return (
    <div className="flex flex-col gap-3">
      <nav aria-label="breadcrumb" className="text-sm text-fg-muted">
        <ol className="flex flex-wrap items-center gap-1">
          <li>
            <Link href="/" className="hover:text-fg">
              {t("portrait.breadcrumbRegistry")}
            </Link>
          </li>
          <ChevronRight className="size-3.5" aria-hidden />
          <li aria-current="page" className="font-medium text-fg">
            {t("portrait.breadcrumbPortrait")}
          </li>
          {shown && (
            <li className="ml-1">
              ·{" "}
              {t("portrait.updated", {
                date: format.dateTime(new Date(shown.meta.finished_at ?? shown.meta.created_at), {
                  dateStyle: "medium",
                }),
              })}
            </li>
          )}
        </ol>
      </nav>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{person.full_name}</h1>
          {person.latin_name && <p className="text-sm text-fg-muted">{person.latin_name}</p>}
        </div>
        <div className="flex flex-wrap gap-2">
          {(detail.versions.length > 0 || canEdit) && (
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="secondary" aria-label={t("portrait.versions")}>
                  <History aria-hidden />
                  {shown
                    ? t("portrait.version", { version: shown.meta.version })
                    : t("portrait.versions")}
                  <ChevronDown aria-hidden />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent className="w-72">
                <DropdownMenuLabel className="text-xs text-fg-muted">
                  {t("portrait.versions")}
                </DropdownMenuLabel>
                {detail.versions.map((version) => (
                  <DropdownMenuItem
                    key={version.id}
                    disabled={version.status !== "done"}
                    onSelect={() => onSelectVersion(version.id)}
                    className="justify-between"
                  >
                    <span>
                      {t("portrait.version", { version: version.version })}
                      {version.id === detail.current?.meta.id && (
                        <span className="ml-1 text-xs text-fg-muted">
                          · {t("portrait.currentVersion")}
                        </span>
                      )}
                      <span className="block text-xs text-fg-muted">
                        {format.dateTime(new Date(version.created_at), {
                          dateStyle: "short",
                          timeStyle: "short",
                        })}
                        {version.status !== "done" && ` · ${t(`jobStatus.${version.status}`)}`}
                      </span>
                    </span>
                    {version.level && <LevelBadge level={version.level} />}
                  </DropdownMenuItem>
                ))}
                {canEdit && <DropdownMenuSeparator />}
                {canEdit && shown && !isCurrent && done && (
                  <DropdownMenuItem onSelect={() => current.mutate(shown.meta.id)}>
                    <ClipboardCheck aria-hidden />
                    {t("portrait.makeCurrent")}
                  </DropdownMenuItem>
                )}
                {canEdit && (
                  <DropdownMenuItem
                    disabled={building || rebuild.isPending}
                    onSelect={() => rebuild.mutate()}
                  >
                    <RefreshCw aria-hidden />
                    {rebuild.isPending ? t("portrait.rebuilding") : t("portrait.newVersion")}
                  </DropdownMenuItem>
                )}
              </DropdownMenuContent>
            </DropdownMenu>
          )}
          {(canEdit || partnerId) && (
            <Button variant="secondary" onClick={() => setDialog("info_request")}>
              <MessageSquarePlus aria-hidden />
              {t("portrait.requestInfo")}
            </Button>
          )}
          {done && (
            <>
              <Button
                variant="secondary"
                disabled={exporter.isPending}
                onClick={() => exporter.mutate("pdf")}
              >
                <FileDown aria-hidden />
                {t("portrait.exportPdf")}
              </Button>
              <Button
                variant="secondary"
                disabled={exporter.isPending}
                onClick={() => exporter.mutate("docx")}
                aria-label={t("portrait.exportDocx")}
                title={t("portrait.exportDocx")}
              >
                <FileText aria-hidden />
                {t("portrait.exportDocxShort")}
              </Button>
            </>
          )}
          {canEdit && done && isCurrent && (
            <Button variant="secondary" onClick={() => setDialog("review")}>
              <ClipboardCheck aria-hidden />
              {t("portrait.review")}
            </Button>
          )}
          {canEdit && detail.current && (
            <Button onClick={() => setDialog("disclosure")}>
              <Send aria-hidden />
              {t("portrait.sendToPartner")}
            </Button>
          )}
        </div>
      </div>
      {exporter.isPending && (
        <p className="text-sm text-fg-muted" role="status">
          {t("portrait.exporting")}
        </p>
      )}
      {(exportError || rebuild.isError || current.isError) && (
        <Alert tone="error">{errorMessage(exportError ?? rebuild.error ?? current.error, t)}</Alert>
      )}

      {(dialog === "info_request" || dialog === "disclosure") && (
        <RequestDialog
          personId={person.id}
          kind={dialog}
          partnerId={partnerId}
          open
          onOpenChange={(open) => !open && setDialog(null)}
        />
      )}
      {dialog === "review" && shown?.portrait && (
        <ReviewDialog
          personId={person.id}
          portraitId={shown.meta.id}
          portrait={shown.portrait}
          review={shown.review}
          open
          onOpenChange={(open) => !open && setDialog(null)}
        />
      )}
    </div>
  );
}

function PortraitBody({
  out,
  personId,
  requests,
  canEdit,
}: {
  out: PortraitOut;
  personId: string;
  requests: readonly ExchangeRequest[];
  canEdit: boolean;
}) {
  const t = useTranslations("portrait");
  const format = useFormatter();
  const portrait = out.portrait!;
  const stats = portrait.stats;
  return (
    <div className="flex flex-col gap-5">
      {portrait.warnings.length > 0 && (
        <section aria-label={t("warningsTitle")} className="flex flex-col gap-2">
          {portrait.warnings.map((warning) => (
            <Alert key={warning} tone="warning">
              {warning}
            </Alert>
          ))}
        </section>
      )}
      <div className="grid gap-5 lg:grid-cols-[300px_minmax(0,1fr)] xl:grid-cols-[300px_minmax(0,1fr)_320px] xl:items-start">
        <div className="flex flex-col gap-5">
          <IdentityCard portrait={portrait} />
          <PepCard pep={portrait.pep} />
        </div>
        <div className="flex min-w-0 flex-col gap-5">
          <RiskScoreCard risk={portrait.risk} />
          <ConclusionCard text={portrait.conclusion} review={out.review} />
          <FactorList factors={portrait.risk.factors} />
          <TimelineCard events={portrait.timeline} />
        </div>
        <div className="flex min-w-0 flex-col gap-5 lg:col-span-2 lg:grid lg:grid-cols-2 xl:col-span-1 xl:flex">
          <RelatedCard portrait={portrait} />
          <SanctionsCard portrait={portrait} />
          <VerificationCard portrait={portrait} requests={requests} />
          <RequestLogCard personId={personId} requests={requests} canEdit={canEdit} />
        </div>
      </div>
      <div className="grid gap-5 lg:grid-cols-2 lg:items-start">
        <PositionsCard positions={portrait.positions} basis={portrait.pep.basis} />
        <AdverseCard portrait={portrait} />
      </div>
      <SourcesList portrait={portrait} />
      <section
        aria-labelledby="limitations-title"
        className="flex flex-col gap-2 text-xs text-fg-muted"
      >
        <h2 id="limitations-title" className="text-sm font-semibold text-fg">
          {t("limitationsTitle")}
        </h2>
        <ul className="flex list-disc flex-col gap-1 pl-4">
          {portrait.limitations.map((limitation) => (
            <li key={limitation}>{limitation}</li>
          ))}
        </ul>
        <p className="mt-1 font-mono">
          {t("stats", {
            queries: stats.queries,
            sources: stats.sources,
            fetched: stats.fetched,
            analyzed: stats.analyzed,
            seconds: format.number(stats.duration_s, { maximumFractionDigits: 0 }),
            model: stats.model ?? t("noModel"),
          })}
        </p>
      </section>
    </div>
  );
}
