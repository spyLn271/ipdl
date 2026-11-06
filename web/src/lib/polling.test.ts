import { portraitOut } from "@/test/fixtures";
import { pollInterval } from "./polling";

describe("pollInterval", () => {
  it("polls every 2 s while the version is being built", () => {
    expect(pollInterval(undefined, null)).toBe(2000);
    expect(
      pollInterval({ ...portraitOut, meta: { ...portraitOut.meta, status: "running" } }, null),
    ).toBe(2000);
  });

  it("stops on a final status or any error (404, 401)", () => {
    expect(pollInterval(portraitOut, null)).toBe(false);
    expect(
      pollInterval({ ...portraitOut, meta: { ...portraitOut.meta, status: "failed" } }, null),
    ).toBe(false);
    expect(pollInterval(undefined, new Error("404"))).toBe(false);
  });
});
