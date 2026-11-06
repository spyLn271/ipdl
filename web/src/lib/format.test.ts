import {
  formatPartialDate,
  formatPeriod,
  initials,
  isBuilding,
  isFinal,
  levelTone,
  scalePosition,
} from "./format";

describe("format helpers", () => {
  it("maps risk levels to tones", () => {
    expect(levelTone("low")).toBe("ok");
    expect(levelTone("medium")).toBe("warning");
    expect(levelTone("high")).toBe("error");
    expect(levelTone("no_data")).toBe("neutral");
    expect(levelTone(null)).toBe("neutral");
  });

  it("builds initials from a full name", () => {
    expect(initials("Иванов Пётр Сергеевич")).toBe("ИП");
    expect(initials("  sheiman  ")).toBe("S");
  });

  it("formats partial dates from sources", () => {
    expect(formatPartialDate("2019", "ru")).toBe("2019");
    expect(formatPartialDate("1958-05-26", "ru")).toBe("26.05.1958");
    expect(formatPartialDate("2024-05", "en")).toBe("May 2024");
    expect(formatPartialDate(null, "ru")).toBe("");
  });

  it("formats periods of office", () => {
    const labels = { since: "с", until: "по", present: "по н. в." };
    expect(formatPeriod("2019", "2023", "ru", labels)).toBe("2019 — 2023");
    expect(formatPeriod("2019", null, "ru", labels, true)).toBe("2019 — по н. в.");
    expect(formatPeriod("2019", null, "ru", labels)).toBe("с 2019");
    expect(formatPeriod(null, "2020", "ru", labels)).toBe("по 2020");
    expect(formatPeriod(null, null, "ru", labels)).toBe("");
  });

  it("knows final and building job states", () => {
    expect(isFinal("done")).toBe(true);
    expect(isFinal("failed")).toBe(true);
    expect(isFinal("running")).toBe(false);
    expect(isBuilding("queued")).toBe(true);
    expect(isBuilding("done")).toBe(false);
  });

  it("keeps the scale marker inside the bar", () => {
    expect(scalePosition(0)).toBe(2);
    expect(scalePosition(55)).toBe(55);
    expect(scalePosition(100)).toBe(98);
  });
});
