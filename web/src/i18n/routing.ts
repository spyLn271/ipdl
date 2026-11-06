import { defineRouting } from "next-intl/routing";

export const routing = defineRouting({
  // ru — основной язык; kk — государственный; en — для зарубежных партнёров (ПФР)
  locales: ["ru", "kk", "en"],
  defaultLocale: "ru",
  // Префикс у всех локалей: «as-needed» в standalone-сборке Next 16.4 зацикливает rewrite
  localePrefix: "always",
});

export type Locale = (typeof routing.locales)[number];
