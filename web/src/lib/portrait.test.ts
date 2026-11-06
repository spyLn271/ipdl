import { type ExchangeRequest } from "@/lib/api/schemas";
import { personDetail, portrait } from "@/test/fixtures";
import { evidenceBySource, exchangeStatus, mainPosition, sourceGroups } from "./portrait";

const partner = { id: "p", country: "UZ", name: "ПФР", contact: null, is_active: true };

function request(patch: Partial<ExchangeRequest>): ExchangeRequest {
  return {
    id: "r",
    partner,
    portrait_id: null,
    direction: "outgoing",
    kind: "info_request",
    status: "open",
    purpose: "проверка",
    legal_basis: null,
    response_note: null,
    created_at: "2026-10-27T20:00:00Z",
    updated_at: "2026-10-27T20:00:00Z",
    closed_at: null,
    created_by_name: null,
    ...patch,
  };
}

describe("portrait helpers", () => {
  it("picks the position the PEP conclusion is based on", () => {
    const position = mainPosition(portrait);
    expect(position).not.toBeNull();
    expect(position).toBe(portrait.positions[portrait.pep.basis[0] ?? 0]);
  });

  it("derives the exchange status from the request log", () => {
    expect(exchangeStatus([])).toBe("not_requested");
    expect(exchangeStatus([request({ kind: "disclosure", status: "closed" })])).toBe(
      "not_requested",
    );
    expect(exchangeStatus([request({ status: "in_progress" })])).toBe("requested");
    expect(exchangeStatus([request({ status: "closed" })])).toBe("received");
  });

  it("summarises sources like the mockup card", () => {
    const groups = sourceGroups(portrait, personDetail.requests);
    expect(groups.map((g) => g.key)).toEqual(["official", "open", "sanctions", "exchange"]);
    expect(groups.find((g) => g.key === "sanctions")?.status).toBe("checked");
    const confirmed = {
      ...portrait,
      sources: portrait.sources.map((s) => ({ ...s, verification: "confirmed" as const })),
    };
    expect(sourceGroups(confirmed, []).find((g) => g.key === "open")?.status).toBe("verified");
  });

  it("groups evidence quotes by source", () => {
    const quotes = evidenceBySource(portrait);
    const withFacts = portrait.sources.find((s) => s.facts > 0);
    expect(withFacts && quotes.get(withFacts.id)?.length).toBeGreaterThan(0);
  });
});
