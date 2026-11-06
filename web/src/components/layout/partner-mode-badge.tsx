"use client";

import { Globe2 } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { countryName } from "@/lib/countries";
import { useSession } from "@/lib/session";

/** Полоса под шапкой, как в макете: «Режим: доступ для зарубежных партнёров (ПФР) · страна · орган». */
export function PartnerModeBar() {
  const t = useTranslations("nav");
  const locale = useLocale();
  const { me } = useSession();
  const partner = me?.user.role === "partner" ? me.user.partner : null;
  if (!partner) return null;
  return (
    <div className="border-t border-border bg-info-subtle text-info-fg">
      <p className="mx-auto flex max-w-page items-center gap-2 px-4 py-1.5 text-xs sm:px-6">
        <Globe2 className="size-3.5 shrink-0" aria-hidden />
        <span className="font-medium">{t("partnerMode")}</span>
        <span aria-hidden>·</span>
        <span className="truncate">
          {countryName(partner.country, locale)} · {partner.name}
        </span>
      </p>
    </div>
  );
}
