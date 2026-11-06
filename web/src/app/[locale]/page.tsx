import { setRequestLocale } from "next-intl/server";
import { AuthGate } from "@/components/auth/auth-gate";
import { RegistryView } from "@/components/registry/registry-view";

export default async function RegistryPage({ params }: { params: Promise<{ locale: string }> }) {
  const { locale } = await params;
  setRequestLocale(locale);
  return (
    <AuthGate>
      <RegistryView />
    </AuthGate>
  );
}
