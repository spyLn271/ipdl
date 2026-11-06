import { type Metadata } from "next";
import { getTranslations, setRequestLocale } from "next-intl/server";
import { AuthGate } from "@/components/auth/auth-gate";
import { NewPersonForm } from "@/components/person/new-person-form";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ locale: string }>;
}): Promise<Metadata> {
  const { locale } = await params;
  const t = await getTranslations({ locale, namespace: "newPerson" });
  return { title: t("title") };
}

export default async function NewPersonPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <AuthGate roles={["admin", "analyst"]}>
      <NewPersonForm />
    </AuthGate>
  );
}
