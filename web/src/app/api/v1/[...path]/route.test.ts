import { NextRequest } from "next/server";
import { GET, POST } from "./route";

function context(...path: string[]) {
  return { params: Promise.resolve({ path }) };
}

describe("API proxy", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("API_URL", "http://api.internal:8000/");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("refuses path segments that would escape /api/v1", async () => {
    for (const segments of [
      ["..", "metrics"],
      ["persons", ".", "x"],
      ["persons", "..", ".."],
    ]) {
      const request = new NextRequest("http://localhost:3000/api/v1/x");
      const response = await GET(request, context(...segments));
      expect(response.status).toBe(404);
    }
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("forwards cookies, CSRF header, body and query to the backend", async () => {
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 201 }));
    const request = new NextRequest("http://localhost:3000/api/v1/persons?x=1", {
      method: "POST",
      body: JSON.stringify({ full_name: "Тест" }),
      headers: {
        cookie: "ipdl_session=s; ipdl_csrf=c",
        "x-csrf-token": "c",
        "content-type": "application/json",
      },
    });
    const response = await POST(request, context("persons"));
    expect(response.status).toBe(201);
    const [target, init] = fetchMock.mock.calls[0]!;
    expect(String(target)).toBe("http://api.internal:8000/api/v1/persons?x=1");
    const headers = new Headers(init?.headers);
    expect(headers.get("cookie")).toBe("ipdl_session=s; ipdl_csrf=c");
    expect(headers.get("x-csrf-token")).toBe("c");
    expect(headers.get("host")).toBeNull();
    expect(init?.method).toBe("POST");
  });

  it("passes every Set-Cookie through and disables caching", async () => {
    const upstream = new Headers({ "content-type": "application/json" });
    upstream.append("set-cookie", "ipdl_session=abc; HttpOnly; Path=/; SameSite=lax");
    upstream.append("set-cookie", "ipdl_csrf=def; Path=/; SameSite=lax");
    fetchMock.mockResolvedValueOnce(new Response("{}", { status: 200, headers: upstream }));
    const response = await POST(
      new NextRequest("http://localhost:3000/api/v1/auth/login", { method: "POST", body: "{}" }),
      context("auth", "login"),
    );
    expect(response.headers.getSetCookie()).toHaveLength(2);
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("encodes path segments and answers 502 when the backend is down", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("connect ECONNREFUSED"));
    const response = await GET(
      new NextRequest("http://localhost:3000/api/v1/persons/a%2Fb"),
      context("persons", "a/b"),
    );
    expect(String(fetchMock.mock.calls[0]![0])).toBe(
      "http://api.internal:8000/api/v1/persons/a%2Fb",
    );
    expect(response.status).toBe(502);
    expect(await response.json()).toMatchObject({ error: { code: "upstream_unavailable" } });
  });
});
