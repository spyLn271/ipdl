"use client";

import { Scale } from "lucide-react";
import { useTranslations } from "next-intl";
import { SectionCard } from "@/components/portrait/section-card";
import { type PepAssessment } from "@/lib/api/schemas";

export function PepCard({ pep }: { pep: PepAssessment }) {
  const t = useTranslations("portrait");
  return (
    <SectionCard title={t("pepTitle")} titleId="pep-title">
      <p className="text-sm text-fg">{pep.rationale}</p>
      {pep.clause && (
        <p className="mt-3 flex items-start gap-2 text-xs text-fg-muted">
          <Scale className="mt-0.5 size-3.5 shrink-0" aria-hidden />
          <span>
            <span className="font-medium text-fg">{t("clause")}:</span> {pep.clause}
          </span>
        </p>
      )}
      {pep.measures.length > 0 && (
        <div className="mt-3">
          <h3 className="text-xs font-medium text-fg">{t("measures")}</h3>
          <ul className="mt-1.5 flex list-disc flex-col gap-1 pl-4 text-xs text-fg-muted">
            {pep.measures.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </div>
      )}
    </SectionCard>
  );
}
