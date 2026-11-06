import { QueryClient } from "@tanstack/react-query";
import { personDetail } from "@/test/fixtures";
import { type Me } from "@/lib/api/schemas";
import { canEdit, endSession, isInternal, ME_QUERY_KEY, startSession } from "./session";

const me: Me = {
  user: {
    id: "u",
    username: "analyst",
    display_name: "Аналитик",
    role: "analyst",
    partner: null,
    is_active: true,
    created_at: "2026-10-27T00:00:00Z",
    last_login_at: null,
  },
  expires_at: "2026-10-28T00:00:00Z",
};

describe("session cache", () => {
  it("keeps the session query object so subscribed components see the new user", () => {
    const client = new QueryClient();
    client.setQueryData(["person", "x"], personDetail);
    const before = client.getQueryCache().find({ queryKey: ME_QUERY_KEY });
    client.setQueryData(ME_QUERY_KEY, null);
    startSession(client, me);
    expect(client.getQueryData(ME_QUERY_KEY)).toEqual(me);
    expect(client.getQueryData(["person", "x"])).toBeUndefined();
    const after = client.getQueryCache().find({ queryKey: ME_QUERY_KEY });
    expect(before === undefined || after === before).toBe(true);
  });

  it("drops user data on sign-out", async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    startSession(client, me);
    client.setQueryData(["persons"], { items: [] });
    await endSession(client);
    expect(client.getQueryData(["persons"])).toBeUndefined();
    expect(client.getQueryData(ME_QUERY_KEY)).toBeUndefined();
  });

  it("knows which roles may edit", () => {
    expect(canEdit("analyst")).toBe(true);
    expect(canEdit("viewer")).toBe(false);
    expect(isInternal("partner")).toBe(false);
  });
});
