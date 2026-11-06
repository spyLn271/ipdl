import { readCsrfToken } from "./csrf";

describe("readCsrfToken", () => {
  it("finds the CSRF cookie among others", () => {
    expect(readCsrfToken("a=1; ipdl_csrf=abc%2Bdef; b=2")).toBe("abc+def");
  });

  it("returns an empty string without the cookie", () => {
    expect(readCsrfToken("ipdl_session_x=1")).toBe("");
    expect(readCsrfToken("")).toBe("");
  });
});
