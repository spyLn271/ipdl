import { type Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AuditSection } from "@/components/admin/audit-section";
import { PartnersSection } from "@/components/admin/partners-section";
import { UsersSection } from "@/components/admin/users-section";
import { AuthGate } from "@/components/auth/auth-gate";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "admin" });
  return { title: t("title") };
}

export default async function AdminPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  const t = await getTranslations({ locale, namespace: "admin" });
  return (
    <AuthGate roles={["admin"]}>
      <div className="flex flex-col gap-10">
        <h1 className="text-2xl font-semibold text-fg sm:text-3xl">{t("title")}</h1>
        <UsersSection />
        <PartnersSection />
        <AuditSection />
      </div>
    </AuthGate>
  );
}
