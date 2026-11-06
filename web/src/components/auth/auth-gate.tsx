"use client";

import { Loader2 } from "lucide-react";
import { useTranslations } from "next-intl";
import { type ReactNode, useEffect } from "react";
import { ErrorState } from "@/components/layout/error-state";
import { usePathname, useRouter } from "@/i18n/navigation";
import { type Role } from "@/lib/api/schemas";
import { useSession } from "@/lib/session";

const PUBLIC_PATHS = new Set(["/login"]);

/**
 * Клиентская проверка входа: без сессии — на /login?next=…; страница с ограничением по ролям
 * (roles) показывает 403-состояние. Права дополнительно проверяет сервер на каждом запросе.
 */
export function AuthGate({ children, roles }: { children: ReactNode; roles?: readonly Role[] }) {
  const t = useTranslations();
  const pathname = usePathname();
  const router = useRouter();
  const { me, isLoading, isAnonymous, error } = useSession();
  const isPublic = PUBLIC_PATHS.has(pathname);

  useEffect(() => {
    if (isAnonymous && !isPublic) {
      const next = `${window.location.pathname.replace(/^\/[a-z]{2}(?=\/|$)/, "") || "/"}${window.location.search}`;
      router.replace(next === "/" ? "/login" : `/login?next=${encodeURIComponent(next)}`);
    }
  }, [isAnonymous, isPublic, router]);

  if (isPublic) return children;
  if (isLoading || isAnonymous) {
    return (
      <div className="flex justify-center py-24 text-fg-muted" role="status" aria-live="polite">
        <Loader2 className="size-5 animate-spin" aria-hidden />
        <span className="sr-only">{t("common.loading")}</span>
      </div>
    );
  }
  if (error || !me) {
    return <ErrorState title={t("errors.loadFailed")} text={t("errors.network")} />;
  }
  if (roles && !roles.includes(me.user.role)) {
    return <ErrorState title={t("errors.forbiddenTitle")} text={t("errors.forbidden")} />;
  }
  return children;
}
