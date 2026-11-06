"use client";

import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { Gauge } from "@/components/charts/gauge";
import { LevelBadge } from "@/components/registry/badges";
import { type RiskAssessment } from "@/lib/api/schemas";
import { LEVEL_FILL, scalePosition } from "@/lib/format";
import { useIsClient } from "@/lib/use-is-client";

const SIZE = 200;

/** Итоговая оценка 0–100: Gauge как балл в Normocontrol, цвет — по уровню риска; шкала из макета. */
export function RiskScoreCard({ risk }: { risk: RiskAssessment }) {
  const t = useTranslations("portrait.risk");
  const tl = useTranslations("levels");
  const format = useFormatter();
  const isClient = useIsClient();
  const score = Math.max(0, Math.min(100, risk.score));
  const height = Math.round(SIZE * 0.62);
  const date = (value: string) => format.dateTime(new Date(value), { dateStyle: "medium" });

  return (
    <section
      aria-labelledby="risk-title"
      className="@container rounded-card-lg border border-border bg-bg p-5 sm:p-6"
      data-level={risk.level}
    >
      <h2 id="risk-title" className="text-base font-semibold text-fg">
        {t("title")}
      </h2>
      <div className="mt-4 grid gap-6 @xl:grid-cols-[auto_minmax(0,1fr)] @xl:items-center">
        <figure
          role="img"
          aria-label={t("aria", { score, level: tl(risk.level) })}
          className="mx-auto flex flex-col items-center"
        >
          <div aria-hidden className="pointer-events-none" style={{ width: SIZE, height }}>
            {isClient && (
              <Gauge
                value={score}
                centerValue={score}
                defaultLabel={t("of100")}
                activeFill={LEVEL_FILL[risk.level]}
                inactiveFillOpacity={0.35}
                totalNotches={40}
                spacing={25}
                width={SIZE}
                height={height}
              />
            )}
          </div>
          <figcaption className="mt-1">
            <LevelBadge level={risk.level} prefix />
          </figcaption>
        </figure>
        <div className="flex min-w-0 flex-col gap-3">
          <div>
            <div className="relative">
              <div className="flex h-2.5 overflow-hidden rounded-badge" aria-hidden>
                <div className="flex-1 bg-ok" />
                <div className="flex-1 bg-warning" />
                <div className="flex-1 bg-error" />
              </div>
              <span
                aria-hidden
                className="absolute -top-1 h-4.5 w-1 -translate-x-1/2 rounded-badge bg-fg ring-2 ring-bg"
                style={{ left: `${scalePosition(score)}%` }}
              />
            </div>
            <div className="mt-1.5 flex justify-between gap-2 text-xs text-fg-muted">
              <span>{t("bandLow")}</span>
              <span className="text-center">{t("bandMedium")}</span>
              <span className="text-right">{t("bandHigh")}</span>
            </div>
          </div>
          <p className="text-sm text-fg-muted">
            {/* Даты вида «28 окт. 2026 г.» уже кончаются точкой — части разделяются «·» */}
            {[
              t("method", { method: risk.method_title }),
              t("assessed", { date: date(risk.assessed_at) }),
              t("nextReview", { date: date(risk.next_review) }),
            ].join(" · ")}
          </p>
          {risk.floors.length > 0 && (
            <ul className="flex flex-col gap-1 text-xs text-warning-fg">
              {risk.floors.map((floor) => (
                <li key={floor}>{t("floor", { reason: floor })}</li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </section>
  );
}
