/** Производные данные портрета для интерфейса: основная должность, сводка проверки источников. */
import {
  type ExchangeRequest,
  type Portrait,
  type Position,
  type Source,
  type SourceKind,
} from "@/lib/api/schemas";

/** Должность, на которой основан вывод о статусе, иначе — первая (самая значимая). */
export function mainPosition(portrait: Portrait): Position | null {
  const index = portrait.pep.basis[0];
  if (index !== undefined && portrait.positions[index]) return portrait.positions[index];
  return portrait.positions[0] ?? null;
}

export type GroupStatus =
  | "verified"
  | "partial"
  | "unverified"
  | "disputed"
  | "not_found"
  | "checked"
  | "not_checked"
  | "not_requested"
  | "requested"
  | "received";

export interface SourceGroup {
  key: "official" | "open" | "sanctions" | "exchange";
  count: number;
  status: GroupStatus;
}

const OFFICIAL_KINDS: ReadonlySet<SourceKind> = new Set(["official"]);

function verificationStatus(sources: readonly Source[]): GroupStatus {
  if (sources.length === 0) return "not_found";
  const confirmed = sources.filter((s) => s.verification === "confirmed").length;
  const disputed = sources.filter((s) => s.verification === "disputed").length;
  if (disputed > 0 && confirmed === 0) return "disputed";
  if (confirmed === sources.length) return "verified";
  if (confirmed > 0 || disputed > 0) return "partial";
  return "unverified";
}

/** Статус обмена с зарубежными ПФР по журналу обращений (запросы доп. информации). */
export function exchangeStatus(requests: readonly ExchangeRequest[]): GroupStatus {
  const asked = requests.filter((r) => r.kind === "info_request" && r.direction === "outgoing");
  if (asked.length === 0) return "not_requested";
  if (asked.some((r) => r.status !== "closed")) return "requested";
  return "received";
}

/** Сводка «Источники и верификация»: как в макете — реестры, СМИ, санкции, обмен с ПФР. */
export function sourceGroups(
  portrait: Portrait,
  requests: readonly ExchangeRequest[],
): SourceGroup[] {
  const used = portrait.sources.filter((s) => s.analyzed || s.fetched || s.facts > 0);
  const pool = used.length > 0 ? used : portrait.sources;
  const official = pool.filter((s) => OFFICIAL_KINDS.has(s.kind));
  const open = pool.filter((s) => !OFFICIAL_KINDS.has(s.kind));
  const asked = requests.filter((r) => r.kind === "info_request" && r.direction === "outgoing");
  return [
    { key: "official", count: official.length, status: verificationStatus(official) },
    { key: "open", count: open.length, status: verificationStatus(open) },
    {
      key: "sanctions",
      count: portrait.sanctions.lists.length,
      status: portrait.sanctions.lists.length > 0 ? "checked" : "not_checked",
    },
    { key: "exchange", count: asked.length, status: exchangeStatus(requests) },
  ];
}

export function groupTone(status: GroupStatus): "ok" | "warning" | "error" | "neutral" {
  switch (status) {
    case "verified":
    case "checked":
    case "received":
      return "ok";
    case "partial":
    case "requested":
    case "unverified":
      return "warning";
    case "disputed":
      return "error";
    default:
      return "neutral";
  }
}

/** Источники по id — для ссылок «[S3]» в факторах и фактах. */
export function sourceIndex(portrait: Portrait): Map<string, Source> {
  return new Map(portrait.sources.map((s) => [s.id, s]));
}

/** Все цитаты портрета, сгруппированные по источнику (для карточек источников). */
export function evidenceBySource(portrait: Portrait): Map<string, string[]> {
  const map = new Map<string, string[]>();
  const add = (sourceId: string, quote: string) => {
    const list = map.get(sourceId) ?? [];
    if (!list.includes(quote)) list.push(quote);
    map.set(sourceId, list);
  };
  const { identity } = portrait;
  for (const field of [identity.birth_date, identity.birth_place]) {
    for (const e of field?.evidence ?? []) add(e.source_id, e.quote);
  }
  for (const item of [
    ...portrait.positions,
    ...portrait.relations,
    ...portrait.companies,
    ...portrait.adverse,
    ...portrait.legal,
  ]) {
    for (const e of item.evidence) add(e.source_id, e.quote);
  }
  return map;
}
