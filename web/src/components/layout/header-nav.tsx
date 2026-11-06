"use client";

import { useTranslations } from "next-intl";
import { NavLink } from "@/components/layout/nav-link";
import { isInternal, useSession } from "@/lib/session";

export function HeaderNav() {
  const t = useTranslations("nav");
  const { me } = useSession();
  if (!me) return null;
  const role = me.user.role;
  return (
    // На узком экране меню прокручивается; затухание справа показывает, что пунктов больше
    <nav
      aria-label="primary"
      className="flex min-w-0 [scrollbar-width:none] items-center gap-1 overflow-x-auto [mask-image:linear-gradient(to_right,black_80%,transparent)] text-sm whitespace-nowrap sm:[mask-image:none]"
    >
      <NavLink href="/">{t("registry")}</NavLink>
      {isInternal(role) && <NavLink href="/sanctions">{t("sanctions")}</NavLink>}
      <NavLink href="/methodology">{t("methodology")}</NavLink>
      {role === "admin" && <NavLink href="/admin">{t("admin")}</NavLink>}
    </nav>
  );
}
