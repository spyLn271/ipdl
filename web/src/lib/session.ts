"use client";

import { type QueryClient, useQuery } from "@tanstack/react-query";
import { getMe } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import { type Me, type Role } from "@/lib/api/schemas";

export const ME_QUERY_KEY = ["me"] as const;

export interface Session {
  me: Me | null;
  isLoading: boolean;
  /** true — сервер ответил 401: нужен вход */
  isAnonymous: boolean;
  error: unknown;
}

export function useSession(): Session {
  const query = useQuery({
    queryKey: ME_QUERY_KEY,
    queryFn: getMe,
    staleTime: 60_000,
    retry: false,
  });
  const isAnonymous = query.error instanceof ApiError && query.error.status === 401;
  return {
    me: query.data ?? null,
    isLoading: query.isPending,
    isAnonymous,
    error: isAnonymous ? null : query.error,
  };
}

export function canEdit(role: Role | null | undefined): boolean {
  return role === "admin" || role === "analyst";
}

export function isInternal(role: Role | null | undefined): boolean {
  return role === "admin" || role === "analyst" || role === "viewer";
}

const notSession = (query: { queryKey: readonly unknown[] }) =>
  query.queryKey[0] !== ME_QUERY_KEY[0];

/**
 * Вход: данные прошлой сессии удаляются, запрос /auth/me получает нового пользователя.
 * Сам запрос «me» не удаляется (как при clear()): на него подписаны шапка и меню, и они
 * должны увидеть обновление без перезагрузки страницы.
 */
export function startSession(client: QueryClient, me: Me): void {
  client.removeQueries({ predicate: notSession });
  client.setQueryData(ME_QUERY_KEY, me);
}

/** Выход или смена пароля: удалить данные и перепроверить /auth/me (ответит 401). */
export function endSession(client: QueryClient): Promise<void> {
  client.removeQueries({ predicate: notSession });
  return client.resetQueries({ queryKey: ME_QUERY_KEY });
}
