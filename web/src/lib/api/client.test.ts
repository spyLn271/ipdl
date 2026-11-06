import {
  buildHeaders,
  createPerson,
  filenameFromDisposition,
  getPerson,
  listPersons,
  saveReview,
} from "./client";
import { ApiError } from "./errors";
import personJson from "@/mocks/person-detail.json";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("API client", () => {
  const fetchMock = vi.fn<typeof fetch>();

  beforeEach(() => {
    fetchMock.mockReset();
    vi.stubGlobal("fetch", fetchMock);
    document.cookie = "ipdl_csrf=token-123; path=/";
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    document.cookie = "ipdl_csrf=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/";
  });

  it("sends the CSRF header only on unsafe methods", () => {
    expect(buildHeaders("GET").get("X-CSRF-Token")).toBeNull();
    expect(buildHeaders("POST").get("X-CSRF-Token")).toBe("token-123");
    expect(buildHeaders("PUT", undefined, true).get("Content-Type")).toBe("application/json");
  });

  it("posts JSON with the CSRF token to the same-origin proxy", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(personJson.person, 201));
    await createPerson({ full_name: "Иванов Пётр Сергеевич", birth_date: "1970-03-05" });
    const [url, init] = fetchMock.mock.calls[0]!;
    expect(url).toBe("/api/v1/persons");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("X-CSRF-Token")).toBe("token-123");
    expect(JSON.parse(String(init?.body))).toMatchObject({ build: true, birth_date: "1970-03-05" });
  });

  it("builds the registry query string and skips empty filters", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ items: [], total: 0, page: 2, page_size: 20 }));
    await listPersons({ q: "  sheiman ", pep: null, level: "high", page: 2, pageSize: 20 });
    expect(fetchMock.mock.calls[0]![0]).toBe(
      "/api/v1/persons?q=sheiman&level=high&page=2&page_size=20",
    );
  });

  it("parses a person detail and the review endpoint", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse(personJson));
    const detail = await getPerson(personJson.person.id);
    expect(detail.current?.portrait?.risk.score).toBe(personJson.current.portrait.risk.score);

    fetchMock.mockResolvedValueOnce(jsonResponse(personJson.current));
    await saveReview(personJson.current.meta.id, {
      pep_category: null,
      pep_tenure: null,
      pep_comment: null,
      conclusion: null,
      factors: { transactions: { level: "low", comment: "СПО не поступали" } },
      sources: {},
    });
    const [url, init] = fetchMock.mock.calls[1]!;
    expect(url).toBe(`/api/v1/portraits/${personJson.current.meta.id}/review`);
    expect(init?.method).toBe("PUT");
  });

  it("turns API errors into ApiError with the server code", async () => {
    fetchMock.mockResolvedValueOnce(
      jsonResponse({ error: { code: "csrf_failed", message: "Проверка CSRF не пройдена" } }, 403),
    );
    await expect(createPerson({ full_name: "Тест Тестов" })).rejects.toMatchObject({
      code: "csrf_failed",
      status: 403,
    });
  });

  it("rejects responses that do not match the schema", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ unexpected: true }));
    await expect(getPerson("x")).rejects.toBeInstanceOf(ApiError);
  });

  it("maps network failures to a network error", async () => {
    fetchMock.mockRejectedValueOnce(new TypeError("fetch failed"));
    await expect(getPerson("x")).rejects.toMatchObject({ code: "network", status: 0 });
  });

  it("reads UTF-8 file names from Content-Disposition", () => {
    const header =
      "attachment; filename=\"ipdl-portrait-v1.pdf\"; filename*=UTF-8''%D0%9F%D0%BE%D1%80%D1%82%D1%80%D0%B5%D1%82.pdf";
    expect(filenameFromDisposition(header, "x.pdf")).toBe("Портрет.pdf");
    expect(filenameFromDisposition('attachment; filename="a.docx"', "x")).toBe("a.docx");
    expect(filenameFromDisposition(null, "fallback.pdf")).toBe("fallback.pdf");
  });
});
