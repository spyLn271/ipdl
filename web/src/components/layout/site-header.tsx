import { getTranslations } from "next-intl/server";
import { HeaderNav } from "@/components/layout/header-nav";
import { LocaleSwitcher } from "@/components/layout/locale-switcher";
import { PartnerModeBar } from "@/components/layout/partner-mode-badge";
import { UserMenu } from "@/components/layout/user-menu";
import { Link } from "@/i18n/navigation";

export async function SiteHeader() {
  const t = await getTranslations("nav");
  return (
    <header className="sticky top-0 z-40 border-b border-border bg-bg/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-page items-center gap-3 px-4 sm:gap-4 sm:px-6">
        <Link
          href="/"
          className="flex items-center gap-2 font-semibold text-fg"
          aria-label={t("home")}
        >
          <span
            aria-hidden
            className="flex size-7 items-center justify-center rounded-button bg-primary font-mono text-xs text-primary-fg"
          >
            IP
          </span>
          <span className="hidden whitespace-nowrap sm:inline">
            IPDL
            <span className="hidden font-normal text-fg-muted xl:inline">
              {" "}
              · {t("systemTitle")}
            </span>
          </span>
        </Link>
        <HeaderNav />
        <div className="ml-auto flex items-center gap-2">
          <LocaleSwitcher />
          <UserMenu />
        </div>
      </div>
      <PartnerModeBar />
    </header>
  );
}
