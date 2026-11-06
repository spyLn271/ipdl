/**
 * Схемы ответов API IPDL (zod) — зеркало src/ipdl/api/schemas.py и src/ipdl/analysis/model.py.
 * Ответ, не прошедший проверку, считается ошибкой: интерфейс не показывает данные «наугад».
 */
import { z } from "zod";

export const RISK_LEVELS = ["low", "medium", "high", "no_data"] as const;
export const PEP_CATEGORIES = [
  "foreign",
  "international_org",
  "domestic",
  "family_or_associate",
  "not_pep",
  "undetermined",
] as const;
export const PEP_TENURES = ["current", "former", "unknown"] as const;
export const POSITION_CATEGORIES = [
  "state_body",
  "public_function",
  "international_org",
  "political_party",
  "private_sector",
  "non_profit",
  "other",
] as const;
export const RELATION_KINDS = [
  "spouse",
  "child",
  "parent",
  "sibling",
  "other_relative",
  "business_partner",
  "associate",
] as const;
export const COMPANY_ROLES = [
  "founder",
  "owner",
  "shareholder",
  "beneficial_owner",
  "director",
  "executive",
  "other",
] as const;
export const ADVERSE_CATEGORIES = [
  "corruption",
  "money_laundering",
  "fraud",
  "sanctions",
  "tax",
  "terrorism",
  "organized_crime",
  "other",
] as const;
export const SEVERITIES = ["low", "medium", "high"] as const;
export const LEGAL_KINDS = [
  "criminal_case",
  "investigation",
  "conviction",
  "civil_case",
  "regulatory_action",
] as const;
export const SOURCE_KINDS = ["official", "reference", "media", "corporate", "other"] as const;
export const VERIFICATIONS = ["unverified", "confirmed", "disputed"] as const;
export const FACTOR_KEYS = [
  "position",
  "jurisdiction",
  "wealth",
  "sanctions",
  "legal",
  "adverse_media",
  "related",
  "transactions",
] as const;
export const ROLES = ["admin", "analyst", "viewer", "partner"] as const;
export const JOB_STATUSES = ["queued", "running", "done", "failed"] as const;
export const STAGES = ["search", "fetch", "sanctions", "extract", "assess"] as const;
export const REQUEST_DIRECTIONS = ["incoming", "outgoing"] as const;
export const REQUEST_KINDS = ["info_request", "disclosure"] as const;
export const REQUEST_STATUSES = ["open", "in_progress", "closed"] as const;

export type RiskLevel = (typeof RISK_LEVELS)[number];
export type PepCategory = (typeof PEP_CATEGORIES)[number];
export type PepTenure = (typeof PEP_TENURES)[number];
export type FactorKey = (typeof FACTOR_KEYS)[number];
export type Verification = (typeof VERIFICATIONS)[number];
export type Role = (typeof ROLES)[number];
export type JobStatus = (typeof JOB_STATUSES)[number];
export type Stage = (typeof STAGES)[number];
export type RequestKind = (typeof REQUEST_KINDS)[number];
export type RequestStatus = (typeof REQUEST_STATUSES)[number];
export type SourceKind = (typeof SOURCE_KINDS)[number];

const datetime = z.string().min(1);
const nullableString = z.string().nullable();

export const apiErrorBodySchema = z.object({
  error: z.object({ code: z.string(), message: z.string() }),
});

// ---------------------------------------------------------------- портрет

export const evidenceSchema = z.object({ source_id: z.string(), quote: z.string() });
export type Evidence = z.infer<typeof evidenceSchema>;

export const subjectSchema = z.object({
  full_name: z.string(),
  latin_name: nullableString.default(null),
  birth_date: nullableString.default(null),
  citizenship: nullableString.default(null),
  context: nullableString.default(null),
});

export const sourceSchema = z.object({
  id: z.string(),
  url: z.string(),
  title: z.string(),
  domain: z.string(),
  kind: z.enum(SOURCE_KINDS),
  snippet: z.string().default(""),
  published: nullableString.default(null),
  retrieved_at: datetime,
  engines: z.array(z.string()).default([]),
  topics: z.array(z.string()).default([]),
  relevance: z.number().default(0),
  fetched: z.boolean().default(false),
  analyzed: z.boolean().default(false),
  facts: z.number().int().default(0),
  verification: z.enum(VERIFICATIONS).default("unverified"),
});
export type Source = z.infer<typeof sourceSchema>;

export const positionSchema = z.object({
  title: z.string(),
  organization: nullableString.default(null),
  country: nullableString.default(null),
  start: nullableString.default(null),
  end: nullableString.default(null),
  is_current: z.boolean().nullable().default(null),
  category: z.enum(POSITION_CATEGORIES).default("other"),
  evidence: z.array(evidenceSchema).default([]),
});
export type Position = z.infer<typeof positionSchema>;

export const relationSchema = z.object({
  name: z.string(),
  relation: z.enum(RELATION_KINDS),
  note: nullableString.default(null),
  is_public_official: z.boolean().nullable().default(null),
  evidence: z.array(evidenceSchema).default([]),
});
export type Relation = z.infer<typeof relationSchema>;

export const companySchema = z.object({
  name: z.string(),
  role: z.enum(COMPANY_ROLES).default("other"),
  share_percent: z.number().nullable().default(null),
  country: nullableString.default(null),
  evidence: z.array(evidenceSchema).default([]),
});
export type Company = z.infer<typeof companySchema>;

export const adverseSchema = z.object({
  category: z.enum(ADVERSE_CATEGORIES),
  summary: z.string(),
  date: nullableString.default(null),
  severity: z.enum(SEVERITIES).default("low"),
  evidence: z.array(evidenceSchema).default([]),
});
export type AdverseItem = z.infer<typeof adverseSchema>;

export const legalSchema = z.object({
  kind: z.enum(LEGAL_KINDS),
  summary: z.string(),
  jurisdiction: nullableString.default(null),
  status: nullableString.default(null),
  date: nullableString.default(null),
  evidence: z.array(evidenceSchema).default([]),
});
export type LegalMatter = z.infer<typeof legalSchema>;

export const timelineEventSchema = z.object({
  date: z.string(),
  summary: z.string(),
  kind: z.string().default("event"),
  source_id: nullableString.default(null),
});
export type TimelineEvent = z.infer<typeof timelineEventSchema>;

export const fieldValueSchema = z.object({
  value: z.string(),
  evidence: z.array(evidenceSchema).default([]),
});

export const identitySchema = z.object({
  full_name: z.string(),
  latin_name: nullableString.default(null),
  birth_date: fieldValueSchema.nullable().default(null),
  birth_place: fieldValueSchema.nullable().default(null),
  citizenship: z.array(z.string()).default([]),
  conflicts: z.record(z.string(), z.array(z.string())).default({}),
});
export type Identity = z.infer<typeof identitySchema>;

export const sanctionsListStatusSchema = z.object({
  id: z.string(),
  name: z.string(),
  published_at: nullableString.default(null),
  fetched_at: nullableString.default(null),
  entries: z.number().int().default(0),
});
export type SanctionsListStatus = z.infer<typeof sanctionsListStatusSchema>;

export const sanctionsMatchSchema = z.object({
  query: nullableString.default(null),
  list_id: z.string(),
  list_name: z.string(),
  entry_ref: z.string(),
  matched_name: z.string(),
  primary_name: z.string(),
  score: z.number(),
  birth_dates: z.array(z.string()).default([]),
  nationalities: z.array(z.string()).default([]),
  programs: z.array(z.string()).default([]),
  listed_on: nullableString.default(null),
  url: nullableString.default(null),
  dob_match: z.boolean().nullable().default(null),
});
export type SanctionsMatch = z.infer<typeof sanctionsMatchSchema>;

export const sanctionsCheckSchema = z.object({
  checked_at: datetime,
  lists: z.array(sanctionsListStatusSchema).default([]),
  matches: z.array(sanctionsMatchSchema).default([]),
  related: z.array(sanctionsMatchSchema).default([]),
});

export const pepAssessmentSchema = z.object({
  category: z.enum(PEP_CATEGORIES),
  tenure: z.enum(PEP_TENURES).default("unknown"),
  clause: nullableString.default(null),
  rationale: z.string(),
  basis: z.array(z.number().int()).default([]),
  measures: z.array(z.string()).default([]),
});
export type PepAssessment = z.infer<typeof pepAssessmentSchema>;

export const factorSchema = z.object({
  key: z.enum(FACTOR_KEYS),
  level: z.enum(RISK_LEVELS),
  auto_level: z.enum(RISK_LEVELS),
  weight: z.number(),
  comment: z.string(),
  evidence: z.array(z.string()).default([]),
  overridden: z.boolean().default(false),
});
export type Factor = z.infer<typeof factorSchema>;

export const riskAssessmentSchema = z.object({
  score: z.number().int().min(0).max(100),
  level: z.enum(RISK_LEVELS),
  method: z.string(),
  method_title: z.string(),
  factors: z.array(factorSchema),
  floors: z.array(z.string()).default([]),
  assessed_at: datetime,
  next_review: z.string(),
});
export type RiskAssessment = z.infer<typeof riskAssessmentSchema>;

export const factorOverrideSchema = z.object({
  level: z.enum(RISK_LEVELS),
  comment: z.string(),
});
export type FactorOverride = z.infer<typeof factorOverrideSchema>;

export const reviewSchema = z.object({
  reviewer: nullableString.default(null),
  reviewed_at: nullableString.default(null),
  pep_category: z.enum(PEP_CATEGORIES).nullable().default(null),
  pep_tenure: z.enum(PEP_TENURES).nullable().default(null),
  pep_comment: nullableString.default(null),
  conclusion: nullableString.default(null),
  factors: z.partialRecord(z.enum(FACTOR_KEYS), factorOverrideSchema).default({}),
  sources: z.record(z.string(), z.enum(VERIFICATIONS)).default({}),
});
export type Review = z.infer<typeof reviewSchema>;

export const runStatsSchema = z.object({
  search_ok: z.boolean().default(true),
  llm_used: z.boolean().default(false),
  queries: z.number().int().default(0),
  results: z.number().int().default(0),
  sources: z.number().int().default(0),
  fetched: z.number().int().default(0),
  analyzed: z.number().int().default(0),
  duration_s: z.number().default(0),
  model: nullableString.default(null),
});

export const portraitSchema = z.object({
  subject: subjectSchema,
  identity: identitySchema,
  pep: pepAssessmentSchema,
  risk: riskAssessmentSchema,
  positions: z.array(positionSchema).default([]),
  relations: z.array(relationSchema).default([]),
  companies: z.array(companySchema).default([]),
  adverse: z.array(adverseSchema).default([]),
  legal: z.array(legalSchema).default([]),
  timeline: z.array(timelineEventSchema).default([]),
  sanctions: sanctionsCheckSchema,
  sources: z.array(sourceSchema).default([]),
  conclusion: z.string(),
  limitations: z.array(z.string()).default([]),
  warnings: z.array(z.string()).default([]),
  stats: runStatsSchema.default(runStatsSchema.parse({})),
  generated_at: datetime,
});
export type Portrait = z.infer<typeof portraitSchema>;

// ---------------------------------------------------------------- реестр, пользователи, обмен

export const metaSchema = z.object({
  system_name: z.string(),
  authority: z.string(),
  home_country: z.string(),
  legal_notice: z.string(),
  version: z.string(),
});
export type Meta = z.infer<typeof metaSchema>;

export const partnerSchema = z.object({
  id: z.string(),
  country: z.string(),
  name: z.string(),
  contact: nullableString,
  is_active: z.boolean(),
});
export type Partner = z.infer<typeof partnerSchema>;
export const partnerListSchema = z.array(partnerSchema);

export const userSchema = z.object({
  id: z.string(),
  username: z.string(),
  display_name: z.string(),
  role: z.enum(ROLES),
  partner: partnerSchema.nullable(),
  is_active: z.boolean(),
  created_at: datetime,
  last_login_at: nullableString,
});
export type User = z.infer<typeof userSchema>;
export const userListSchema = z.array(userSchema);

export const meSchema = z.object({ user: userSchema, expires_at: datetime });
export type Me = z.infer<typeof meSchema>;

export const portraitMetaSchema = z.object({
  id: z.string(),
  version: z.number().int(),
  status: z.enum(JOB_STATUSES),
  stage: z.string().nullable(),
  progress: z.number().int(),
  error: nullableString,
  created_at: datetime,
  started_at: nullableString,
  finished_at: nullableString,
  reviewed_at: nullableString,
  created_by_name: nullableString.default(null),
  score: z.number().int().nullable().default(null),
  level: z.enum(RISK_LEVELS).nullable().default(null),
});
export type PortraitMeta = z.infer<typeof portraitMetaSchema>;

export const personSummarySchema = z.object({
  id: z.string(),
  full_name: z.string(),
  latin_name: nullableString,
  birth_date: nullableString,
  citizenship: nullableString,
  context: nullableString,
  pep_category: z.enum(PEP_CATEGORIES).nullable(),
  pep_tenure: z.enum(PEP_TENURES).nullable(),
  position: nullableString,
  organization: nullableString,
  country: nullableString,
  risk_score: z.number().int().nullable(),
  risk_level: z.enum(RISK_LEVELS).nullable(),
  created_at: datetime,
  updated_at: datetime,
  latest: portraitMetaSchema.nullable().default(null),
});
export type PersonSummary = z.infer<typeof personSummarySchema>;

export const personListSchema = z.object({
  items: z.array(personSummarySchema),
  total: z.number().int(),
  page: z.number().int(),
  page_size: z.number().int(),
});
export type PersonList = z.infer<typeof personListSchema>;

export const requestSchema = z.object({
  id: z.string(),
  partner: partnerSchema,
  portrait_id: nullableString,
  direction: z.enum(REQUEST_DIRECTIONS),
  kind: z.enum(REQUEST_KINDS),
  status: z.enum(REQUEST_STATUSES),
  purpose: z.string(),
  legal_basis: nullableString,
  response_note: nullableString,
  created_at: datetime,
  updated_at: datetime,
  closed_at: nullableString,
  created_by_name: nullableString.default(null),
});
export type ExchangeRequest = z.infer<typeof requestSchema>;

export const portraitOutSchema = z.object({
  meta: portraitMetaSchema,
  person_id: z.string(),
  portrait: portraitSchema.nullable(),
  review: reviewSchema.nullable(),
});
export type PortraitOut = z.infer<typeof portraitOutSchema>;

export const personDetailSchema = z.object({
  person: personSummarySchema,
  current: portraitOutSchema.nullable(),
  versions: z.array(portraitMetaSchema),
  requests: z.array(requestSchema),
  can_edit: z.boolean(),
});
export type PersonDetail = z.infer<typeof personDetailSchema>;

// ---------------------------------------------------------------- санкции, методика, аудит

export const sanctionsListOutSchema = sanctionsListStatusSchema.extend({
  url: z.string(),
  status: z.string(),
  error: nullableString,
  stale: z.boolean(),
});
export type SanctionsListOut = z.infer<typeof sanctionsListOutSchema>;
export const sanctionsListsSchema = z.array(sanctionsListOutSchema);

export const sanctionsSearchSchema = z.object({
  query: z.string(),
  matches: z.array(sanctionsMatchSchema),
  lists: z.array(sanctionsListStatusSchema),
});
export type SanctionsSearch = z.infer<typeof sanctionsSearchSchema>;

export const jobAcceptedSchema = z.object({ job: z.string(), status: z.literal("queued") });

export const auditEventSchema = z.object({
  id: z.number().int(),
  at: datetime,
  username: nullableString,
  action: z.string(),
  object_type: nullableString,
  object_id: nullableString,
  ip: nullableString,
  details: z.record(z.string(), z.unknown()).nullable(),
});
export type AuditEvent = z.infer<typeof auditEventSchema>;
export const auditListSchema = z.object({
  items: z.array(auditEventSchema),
  total: z.number().int(),
});
export type AuditList = z.infer<typeof auditListSchema>;

const levelBand = z.tuple([z.number(), z.number()]);
export const methodologySchema = z.object({
  risk_model: z.object({
    id: z.string(),
    title: z.string(),
    bands: z.record(z.string(), levelBand),
    points: z.record(z.string(), z.number()),
    no_data_points: z.number(),
    review_months: z.record(z.string(), z.number()),
    factors: z.record(z.string(), z.object({ weight: z.number(), title: z.string() })),
    floors: z.record(z.string(), z.object({ min_score: z.number(), reason: z.string() })),
    legal_basis: z.record(z.string(), z.unknown()),
  }),
  jurisdictions: z.object({
    fatf: z.object({
      as_of: z.string(),
      review_after_days: z.number(),
      source: z.string(),
      source_url: z.string(),
      call_for_action: z.record(z.string(), z.string()),
      increased_monitoring: z.array(z.string()),
    }),
    preferential_tax: z.object({
      as_of: z.string(),
      source: z.string(),
      source_url: z.string(),
      codes: z.array(z.string()),
      partial: z.record(z.string(), z.string()).default({}),
    }),
    national_high_risk: z.record(z.string(), z.string()).default({}),
  }),
  sanctions_sources: z.array(
    z.object({
      id: z.string(),
      name: z.string(),
      short: z.string(),
      url: z.string(),
      format: z.string(),
      entry_url: z.string().nullable(),
    }),
  ),
});
export type Methodology = z.infer<typeof methodologySchema>;
