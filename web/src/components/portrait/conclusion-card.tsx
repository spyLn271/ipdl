"use client";

import { useTranslations } from "next-intl";
import { useFormatter } from "@/lib/use-formatter";
import { SectionCard } from "@/components/portrait/section-card";
import { type Review } from "@/lib/api/schemas";

export function ConclusionCard({ text, review }: { text: string; review: Review | null }) {
  const t = useTranslations("portrait");
  const format = useFormatter();
  return (
    <SectionCard title={t("conclusionTitle")} titleId="conclusion-title">
      <p className="text-sm leading-relaxed whitespace-pre-line text-fg">{text}</p>
      {review?.reviewer && review.reviewed_at && (
        <p className="mt-3 text-xs text-info-fg">
          {t("reviewedBy", {
            name: review.reviewer,
            date: format.dateTime(new Date(review.reviewed_at), {
              dateStyle: "medium",
              timeStyle: "short",
            }),
          })}
        </p>
      )}
    </SectionCard>
  );
}
