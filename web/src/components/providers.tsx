"use client";

import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { ApiError } from "@/lib/api/errors";
import { ME_QUERY_KEY } from "@/lib/session";

function createClient(): QueryClient {
  // Сессия истекла посреди работы → перепроверить /auth/me: AuthGate отправит на страницу входа
  const expired = (error: unknown) => error instanceof ApiError && error.status === 401;
  const client: QueryClient = new QueryClient({
    queryCache: new QueryCache({
      onError: (error, query) => {
        // 401 у самого /auth/me — это и есть ответ «не вошёл»; перезапрос дал бы цикл
        if (expired(error) && query.queryKey[0] !== ME_QUERY_KEY[0]) {
          void client.invalidateQueries({ queryKey: ME_QUERY_KEY });
        }
      },
    }),
    mutationCache: new MutationCache({
      onError: (error) => {
        if (expired(error)) void client.invalidateQueries({ queryKey: ME_QUERY_KEY });
      },
    }),
    defaultOptions: {
      queries: {
        staleTime: 30_000,
        refetchOnWindowFocus: false,
        retry: (count, error) =>
          !(error instanceof ApiError && error.status >= 400 && error.status < 500) && count < 1,
      },
      mutations: { retry: 0 },
    },
  });
  return client;
}

export function Providers({ children }: { children: ReactNode }) {
  const [client] = useState(createClient);
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}
