import { countryName } from "@/lib/countries";
import { formatPartialDate } from "@/lib/format";
import { kazakhDateTime } from "@/lib/use-formatter";

describe("Kazakh locale fallbacks", () => {
  it("formats dates numerically instead of ICU's «2026 M10 28»", () => {
    const date = new Date(Date.UTC(2026, 9, 28, 9, 5));
    expect(kazakhDateTime(date, { dateStyle: "medium", timeZone: "UTC" })).toBe("28.10.2026");
    expect(kazakhDateTime(date, { dateStyle: "short", timeStyle: "short", timeZone: "UTC" })).toBe(
      "28.10.2026, 09:05",
    );
    expect(formatPartialDate("1958-05-26", "kk")).toBe("26.05.1958");
    expect(formatPartialDate("2019-05", "kk")).toBe("05.2019");
    expect(formatPartialDate("2019", "kk")).toBe("2019");
  });

  it("names countries in Kazakh", () => {
    expect(countryName("KZ", "kk")).toBe("Қазақстан");
    expect(countryName("uz", "kk")).toBe("Өзбекстан");
    expect(countryName("KZ", "ru")).toBe("Казахстан");
  });
});
