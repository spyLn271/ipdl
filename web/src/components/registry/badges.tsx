"use client";

import { useTranslations } from "next-intl";
import { Badge, type BadgeProps } from "@/components/ui/badge";
import { type PepCategory, type PepTenure, type RiskLevel } from "@/lib/api/schemas";
import { levelTone } from "@/lib/format";

const PEP_TONE: Record<PepCategory, NonNullable<BadgeProps["tone"]>> = {
  foreign: "accent",
  international_org: "accent",
  domestic: "info",
  family_or_associate: "info",
  not_pep: "outline",
  undetermined: "neutral",
};

export function PepBadge({
  category,
  tenure,
  className,
}: {
  category: PepCategory;
  tenure?: PepTenure | null;
  className?: string;
}) {
  const t = useTranslations();
  const showTenure =
    tenure && tenure !== "unknown" && category !== "not_pep" && category !== "undetermined";
  return (
    <Badge tone={PEP_TONE[category]} className={className} title={t(`pepLong.${category}`)}>
      {t(`pep.${category}`)}
      {showTenure && <span className="font-normal opacity-80">· {t(`tenure.${tenure}`)}</span>}
    </Badge>
  );
}

export function LevelBadge({
  level,
  prefix = false,
  className,
}: {
  level: RiskLevel;
  prefix?: boolean;
  className?: string;
}) {
  const t = useTranslations();
  const tone = levelTone(level);
  const label = t(`levels.${level}`);
  return (
    <Badge tone={tone === "neutral" ? "neutral" : tone} className={className} data-level={level}>
      <span aria-hidden className="size-1.5 rounded-full bg-current" />
      {prefix ? t("portrait.risk.level", { level: label }) : label}
    </Badge>
  );
}
