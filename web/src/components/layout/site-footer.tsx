"use client";

import { useQuery } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { getMeta } from "@/lib/api/client";

export function SiteFooter() {
  const t = useTranslations("footer");
  const meta = useQuery({ queryKey: ["meta"], queryFn: getMeta, staleTime: Infinity });
  return (
    <footer className="border-t border-border">
      <div className="mx-auto flex max-w-page flex-col gap-2 px-4 py-6 text-xs text-fg-muted sm:flex-row sm:items-start sm:justify-between sm:px-6">
        <p className="flex max-w-3xl items-start gap-2">
          <ShieldCheck className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden />
          <span>{meta.data?.legal_notice ?? t("note")}</span>
        </p>
        {meta.data && (
          <p className="shrink-0">
            {meta.data.system_name} · {meta.data.authority} ·{" "}
            {t("version", { version: meta.data.version })}
          </p>
        )}
      </div>
    </footer>
  );
}
