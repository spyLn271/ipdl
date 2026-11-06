import methodologyJson from "@/mocks/methodology.json";
import personJson from "@/mocks/person-detail.json";
import { methodologySchema, personDetailSchema, portraitSchema, reviewSchema } from "./schemas";

describe("API schemas", () => {
  it("parse a real person detail response", () => {
    const detail = personDetailSchema.parse(personJson);
    expect(detail.person.full_name).toBe("Иванов Пётр Сергеевич");
    const portrait = detail.current?.portrait;
    expect(portrait?.risk.factors).toHaveLength(8);
    expect(portrait?.sanctions.lists.length).toBeGreaterThan(0);
    expect(portrait?.sources.every((s) => /^S\d+$/.test(s.id))).toBe(true);
  });

  it("parse the methodology", () => {
    const methodology = methodologySchema.parse(methodologyJson);
    const weights = Object.values(methodology.risk_model.factors).reduce(
      (sum, f) => sum + f.weight,
      0,
    );
    expect(weights).toBeCloseTo(1);
    expect(methodology.jurisdictions.fatf.increased_monitoring).toContain("BA");
  });

  it("reject an unknown risk level", () => {
    const bad = structuredClone(personJson) as {
      current: { portrait: { risk: { level: string } } };
    };
    bad.current.portrait.risk.level = "extreme";
    expect(portraitSchema.safeParse(bad.current.portrait).success).toBe(false);
  });

  it("fill review defaults", () => {
    expect(reviewSchema.parse({})).toMatchObject({ factors: {}, sources: {}, pep_category: null });
  });
});
