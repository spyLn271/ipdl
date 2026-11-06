import { safeNext } from "./navigation";

describe("safeNext", () => {
  it("allows only relative paths inside the site", () => {
    expect(safeNext("/persons/1")).toBe("/persons/1");
    expect(safeNext(null)).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("/\\evil.example")).toBe("/");
  });
});
