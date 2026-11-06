/**
 * Прокси /api/v1/* → FastAPI IPDL. Адрес бэкенда читается во время работы (API_URL), а не при
 * сборке, поэтому один Docker-образ подходит для любого окружения. Браузер обращается только к
 * своему домену: cookie сессии (httpOnly) и CSRF-cookie живут на нём, CORS не нужен.
 *
 * Cookie запроса и все Set-Cookie ответа передаются как есть; ответы не кэшируются — в них
 * персональные данные.
 */
import { type NextRequest } from "next/server";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

const UPSTREAM_TIMEOUT_MS = 120_000;
// Заголовки соединения и те, что fetch пересчитывает сам (тело уже распаковано)
const HOP_BY_HOP = new Set([
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
  "host",
  "content-length",
  "content-encoding",
]);
const SKIP_RESPONSE = new Set([...HOP_BY_HOP, "set-cookie"]);

interface RouteContext {
  params: Promise<{ path: string[] }>;
}

function apiBaseUrl(): string {
  return (process.env.API_URL ?? "http://127.0.0.1:8000").replace(/\/+$/, "");
}

function requestHeaders(request: NextRequest): Headers {
  const headers = new Headers();
  request.headers.forEach((value, key) => {
    if (!HOP_BY_HOP.has(key.toLowerCase())) headers.set(key, value);
  });
  headers.set("x-forwarded-proto", request.nextUrl.protocol.replace(":", ""));
  const host = request.headers.get("host");
  if (host) headers.set("x-forwarded-host", host);
  return headers;
}

function responseHeaders(upstream: Response): Headers {
  const headers = new Headers();
  upstream.headers.forEach((value, key) => {
    if (!SKIP_RESPONSE.has(key.toLowerCase())) headers.set(key, value);
  });
  // Несколько Set-Cookie (сессия + CSRF) нельзя склеивать в одну строку
  for (const cookie of upstream.headers.getSetCookie()) headers.append("set-cookie", cookie);
  headers.set("cache-control", "no-store");
  return headers;
}

async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path } = await context.params;
  // «..» (в том числе как %2e%2e) вывел бы запрос за пределы /api/v1 — например, к /metrics
  if (path.some((segment) => segment === "." || segment === "..")) {
    return Response.json(
      { error: { code: "not_found", message: "Not found" } },
      { status: 404, headers: { "cache-control": "no-store" } },
    );
  }
  const target = new URL(`${apiBaseUrl()}/api/v1/${path.map(encodeURIComponent).join("/")}`);
  target.search = request.nextUrl.search;

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const init: RequestInit & { duplex?: "half" } = {
    method: request.method,
    headers: requestHeaders(request),
    redirect: "manual",
    cache: "no-store",
    signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    ...(hasBody ? { body: request.body, duplex: "half" } : {}),
  };

  let upstream: Response;
  try {
    upstream = await fetch(target, init);
  } catch {
    return Response.json(
      {
        error: {
          code: "upstream_unavailable",
          message: "Сервис IPDL временно недоступен. Попробуйте позже.",
        },
      },
      { status: 502, headers: { "cache-control": "no-store" } },
    );
  }
  return new Response(upstream.body, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders(upstream),
  });
}

export {
  proxy as DELETE,
  proxy as GET,
  proxy as HEAD,
  proxy as PATCH,
  proxy as POST,
  proxy as PUT,
};
