import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderOptions } from "@testing-library/react";
import { NextIntlClientProvider } from "next-intl";
import { type ReactElement, type ReactNode } from "react";
import en from "../../messages/en.json";
import kk from "../../messages/kk.json";
import ru from "../../messages/ru.json";

const MESSAGES = { ru, kk, en } as const;

export function renderWithProviders(
  ui: ReactElement,
  { locale = "ru", ...options }: RenderOptions & { locale?: keyof typeof MESSAGES } = {},
) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <NextIntlClientProvider locale={locale} messages={MESSAGES[locale]} timeZone="Asia/Almaty">
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      </NextIntlClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper, ...options });
}
