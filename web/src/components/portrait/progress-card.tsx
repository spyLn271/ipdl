"use client";

import { Check, Circle, Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { type PortraitMeta, STAGES, type Stage } from "@/lib/api/schemas";
import { cn } from "@/lib/utils";

function stageIndex(stage: string | null): number {
  const index = STAGES.indexOf((stage ?? "search") as Stage);
  return index === -1 ? 0 : index;
}

/** Ход построения портрета: этапы пайплайна и процент (обновляется опросом раз в 2 с). */
export function ProgressCard({ meta }: { meta: PortraitMeta }) {
  const t = useTranslations();
  const queued = meta.status === "queued";
  const current = queued ? -1 : stageIndex(meta.stage);
  const percent = queued ? 0 : meta.progress;
  return (
    <section
      aria-labelledby="progress-title"
      className="rounded-card-lg border border-border bg-bg p-5 sm:p-6"
      data-status={meta.status}
    >
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="progress-title" className="flex items-center gap-2 text-base font-semibold text-fg">
          <Loader2 className="size-4 animate-spin text-accent" aria-hidden />
          {t("portrait.progress.title")} · {t("portrait.version", { version: meta.version })}
        </h2>
        <span className="font-mono text-sm text-fg" aria-hidden>
          {t("portrait.progress.percent", { percent })}
        </span>
      </div>
      <div
        className="mt-4 h-2 overflow-hidden rounded-badge bg-bg-subtle"
        role="progressbar"
        aria-label={t("portrait.progress.title")}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={percent}
      >
        <div
          className="h-full bg-accent transition-[width] duration-500"
          style={{ width: `${percent}%` }}
        />
      </div>
      {queued && <p className="mt-3 text-sm text-fg-muted">{t("portrait.progress.queued")}</p>}
      <ol className="mt-5 grid gap-2 sm:grid-cols-5" aria-live="polite">
        {STAGES.map((stage, index) => {
          const done = index < current;
          const active = index === current;
          return (
            <li
              key={stage}
              aria-current={active ? "step" : undefined}
              className={cn(
                "flex items-start gap-2 rounded-card border p-3 text-xs",
                active
                  ? "border-accent bg-accent-subtle/40 text-fg"
                  : "border-border text-fg-muted",
                done && "text-fg",
              )}
            >
              {done ? (
                <Check className="mt-0.5 size-3.5 shrink-0 text-ok" aria-hidden />
              ) : active ? (
                <Loader2
                  className="mt-0.5 size-3.5 shrink-0 animate-spin text-accent"
                  aria-hidden
                />
              ) : (
                <Circle className="mt-0.5 size-3.5 shrink-0" aria-hidden />
              )}
              <span>{t(`stages.${stage}`)}</span>
            </li>
          );
        })}
      </ol>
      <p className="mt-4 text-xs text-fg-muted">{t("portrait.progress.hint")}</p>
    </section>
  );
}
