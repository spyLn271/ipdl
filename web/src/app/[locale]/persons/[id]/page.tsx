import { setRequestLocale } from "next-intl/server";
import { AuthGate } from "@/components/auth/auth-gate";
import { PortraitView } from "@/components/portrait/portrait-view";

interface PageProps {
  params: Promise<{ locale: string; id: string }>;
}

export default async function PersonPage({ params }: PageProps) {
  const { locale, id } = await params;
  setRequestLocale(locale);
  return (
    <AuthGate>
      <PortraitView personId={id} />
    </AuthGate>
  );
}
