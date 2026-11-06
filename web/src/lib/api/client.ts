/**
 * Клиент HTTP API IPDL. Все запросы идут на свой домен (/api/v1 — прокси Next.js), cookie
 * сессии браузер отправляет сам; изменяющие запросы несут заголовок X-CSRF-Token.
 */
import { type z } from "zod";
import { CSRF_HEADER, readCsrfToken } from "./csrf";
import { ApiError, errorFromResponse } from "./errors";
import {
  type AuditList,
  auditListSchema,
  type ExchangeRequest,
  jobAcceptedSchema,
  type Me,
  meSchema,
  type Meta,
  metaSchema,
  type Methodology,
  methodologySchema,
  type Partner,
  partnerListSchema,
  partnerSchema,
  type PepCategory,
  type PepTenure,
  type PersonDetail,
  personDetailSchema,
  type PersonList,
  personListSchema,
  type PersonSummary,
  personSummarySchema,
  type PortraitMeta,
  portraitMetaSchema,
  type PortraitOut,
  portraitOutSchema,
  type RequestKind,
  type RequestStatus,
  requestSchema,
  type FactorKey,
  type FactorOverride,
  type RiskLevel,
  type Role,
  type SanctionsListOut,
  sanctionsListsSchema,
  type SanctionsSearch,
  sanctionsSearchSchema,
  type User,
  userListSchema,
  userSchema,
  type Verification,
} from "./schemas";

export const API_BASE = "/api/v1";

const SAFE_METHODS = new Set(["GET", "HEAD", "OPTIONS"]);

/** Заголовки запроса: JSON и CSRF-токен для изменяющих методов. */
export function buildHeaders(method: string, init?: HeadersInit, hasJsonBody = false): Headers {
  const headers = new Headers(init);
  headers.set("Accept", "application/json");
  if (hasJsonBody) headers.set("Content-Type", "application/json");
  if (!SAFE_METHODS.has(method.toUpperCase())) {
    const token = readCsrfToken();
    if (token) headers.set(CSRF_HEADER, token);
  }
  return headers;
}

async function send(path: string, method: string, body?: unknown): Promise<Response> {
  const hasBody = body !== undefined;
  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      method,
      credentials: "same-origin",
      cache: "no-store",
      headers: buildHeaders(method, undefined, hasBody),
      ...(hasBody ? { body: JSON.stringify(body) } : {}),
    });
  } catch {
    throw new ApiError("network", "network", 0);
  }
  if (!response.ok) throw await errorFromResponse(response);
  return response;
}

async function request<T>(
  path: string,
  schema: z.ZodType<T>,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const response = await send(path, method, body);
  const data: unknown = await response.json();
  const parsed = schema.safeParse(data);
  if (!parsed.success) {
    if (process.env.NODE_ENV !== "production") console.error(parsed.error);
    throw new ApiError("invalid_response", "invalid_response", response.status);
  }
  return parsed.data;
}

async function requestVoid(path: string, method: string, body?: unknown): Promise<void> {
  await send(path, method, body);
}

function query(params: Record<string, string | number | null | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") search.set(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : "";
}

const id = (value: string) => encodeURIComponent(value);

// ---------------------------------------------------------------- сессия

export const getMeta = (): Promise<Meta> => request("/meta", metaSchema);
export const getMe = (): Promise<Me> => request("/auth/me", meSchema);
export const login = (username: string, password: string): Promise<Me> =>
  request("/auth/login", meSchema, "POST", { username, password });
export const logout = (): Promise<void> => requestVoid("/auth/logout", "POST");
export const changePassword = (currentPassword: string, newPassword: string): Promise<void> =>
  requestVoid("/auth/password", "POST", {
    current_password: currentPassword,
    new_password: newPassword,
  });

// ---------------------------------------------------------------- реестр

export interface PersonFilter {
  q?: string;
  pep?: PepCategory | null;
  level?: RiskLevel | null;
  page?: number;
  pageSize?: number;
}

export const listPersons = (filter: PersonFilter = {}): Promise<PersonList> =>
  request(
    `/persons${query({
      q: filter.q?.trim(),
      pep: filter.pep,
      level: filter.level,
      page: filter.page,
      page_size: filter.pageSize,
    })}`,
    personListSchema,
  );

export interface PersonInput {
  full_name: string;
  latin_name?: string | null;
  birth_date?: string | null;
  citizenship?: string | null;
  context?: string | null;
}

export const createPerson = (input: PersonInput, build = true): Promise<PersonSummary> =>
  request("/persons", personSummarySchema, "POST", { ...input, build });
export const getPerson = (personId: string): Promise<PersonDetail> =>
  request(`/persons/${id(personId)}`, personDetailSchema);
export const updatePerson = (
  personId: string,
  input: Partial<PersonInput>,
): Promise<PersonSummary> =>
  request(`/persons/${id(personId)}`, personSummarySchema, "PATCH", input);
export const deletePerson = (personId: string): Promise<void> =>
  requestVoid(`/persons/${id(personId)}`, "DELETE");
export const rebuildPortrait = (personId: string): Promise<PortraitMeta> =>
  request(`/persons/${id(personId)}/portraits`, portraitMetaSchema, "POST");

export const getPortrait = (portraitId: string): Promise<PortraitOut> =>
  request(`/portraits/${id(portraitId)}`, portraitOutSchema);
export const makeCurrent = (portraitId: string): Promise<void> =>
  requestVoid(`/portraits/${id(portraitId)}/current`, "POST");

export interface ReviewInput {
  pep_category: PepCategory | null;
  pep_tenure: PepTenure | null;
  pep_comment: string | null;
  conclusion: string | null;
  factors: Partial<Record<FactorKey, FactorOverride>>;
  sources: Record<string, Verification>;
}

export const saveReview = (portraitId: string, review: ReviewInput): Promise<PortraitOut> =>
  request(`/portraits/${id(portraitId)}/review`, portraitOutSchema, "PUT", review);

export type ExportFormat = "pdf" | "docx";

/** Файл экспорта (PDF/DOCX) и имя из Content-Disposition. */
export async function exportPortrait(
  portraitId: string,
  format: ExportFormat,
): Promise<{ blob: Blob; filename: string }> {
  const response = await send(`/portraits/${id(portraitId)}/export.${format}`, "GET");
  return {
    blob: await response.blob(),
    filename: filenameFromDisposition(
      response.headers.get("content-disposition"),
      `ipdl-portrait.${format}`,
    ),
  };
}

export function filenameFromDisposition(header: string | null, fallback: string): string {
  if (!header) return fallback;
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header);
  if (encoded?.[1]) {
    try {
      return decodeURIComponent(encoded[1]);
    } catch {
      // некорректная кодировка — берём ASCII-имя ниже
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header);
  return plain?.[1] ?? fallback;
}

// ---------------------------------------------------------------- обмен с ПФР

export const listPartners = (): Promise<Partner[]> => request("/partners", partnerListSchema);
export const createPartner = (input: {
  country: string;
  name: string;
  contact?: string | null;
}): Promise<Partner> => request("/partners", partnerSchema, "POST", input);
export const updatePartner = (
  partnerId: string,
  input: { name?: string; contact?: string | null; is_active?: boolean },
): Promise<Partner> => request(`/partners/${id(partnerId)}`, partnerSchema, "PATCH", input);

export interface RequestInput {
  partner_id: string;
  kind: RequestKind;
  direction?: "incoming" | "outgoing";
  purpose: string;
  legal_basis?: string | null;
}

export const createRequest = (personId: string, input: RequestInput): Promise<ExchangeRequest> =>
  request(`/persons/${id(personId)}/requests`, requestSchema, "POST", input);
export const updateRequest = (
  requestId: string,
  input: { status?: RequestStatus; response_note?: string | null },
): Promise<ExchangeRequest> => request(`/requests/${id(requestId)}`, requestSchema, "PATCH", input);

// ---------------------------------------------------------------- администрирование

export const listUsers = (): Promise<User[]> => request("/users", userListSchema);
export const createUser = (input: {
  username: string;
  display_name: string;
  password: string;
  role: Role;
  partner_id?: string | null;
}): Promise<User> => request("/users", userSchema, "POST", input);
export const updateUser = (
  userId: string,
  input: {
    display_name?: string;
    role?: Role;
    partner_id?: string | null;
    is_active?: boolean;
    password?: string;
  },
): Promise<User> => request(`/users/${id(userId)}`, userSchema, "PATCH", input);

export const listAudit = (
  filter: { action?: string; page?: number; pageSize?: number } = {},
): Promise<AuditList> =>
  request(
    `/audit${query({ action: filter.action, page: filter.page, page_size: filter.pageSize })}`,
    auditListSchema,
  );

// ---------------------------------------------------------------- санкции и методика

export const listSanctions = (): Promise<SanctionsListOut[]> =>
  request("/sanctions/lists", sanctionsListsSchema);
export const updateSanctions = (): Promise<void> =>
  request("/sanctions/update", jobAcceptedSchema, "POST").then(() => undefined);
export const searchSanctions = (input: {
  q: string;
  birthDate?: string | null;
  kind: "person" | "entity";
}): Promise<SanctionsSearch> =>
  request(
    `/sanctions/search${query({ q: input.q, birth_date: input.birthDate, kind: input.kind })}`,
    sanctionsSearchSchema,
  );

export const getMethodology = (): Promise<Methodology> =>
  request("/methodology", methodologySchema);
