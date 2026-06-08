import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { waitFor, act } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, fetchOptions, mockJson } from "../../../test-utils/renderHook.jsx";
import { queryKeys } from "../../../api/queryKeys.js";
import {
  useWorldQuery,
  useWorldPlacesQuery,
  useWorldNpcsQuery,
  useWorldFactionsQuery,
  useWorldItemsQuery,
  useWorldInventoryQuery,
  useWorldRelationshipsQuery,
  useWorldLoreQuery,
  useDeleteWorldMutation,
} from "./useWorldDetailQuery.js";

describe("useWorldDetailQuery", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("the 7 sub-queries each hit their own endpoint with the worldId", async () => {
    fetchSpy.mockImplementation(async (url) => {
      const u = url.toString();
      if (u.endsWith("/worlds/w1")) return mockJson({ world: { id: "w1", title: "W" } });
      if (u.endsWith("/worlds/w1/places")) return mockJson({ places: [] });
      if (u.endsWith("/worlds/w1/npcs")) return mockJson({ npcs: [] });
      if (u.endsWith("/worlds/w1/factions")) return mockJson({ factions: [] });
      if (u.endsWith("/worlds/w1/items")) return mockJson({ items: [] });
      if (u.endsWith("/worlds/w1/npc-inventory")) return mockJson({ inventory: [] });
      if (u.endsWith("/worlds/w1/relationships")) return mockJson({ relationships: [] });
      throw new Error(`Unmocked URL: ${u}`);
    });

    renderHookWithClient(() => ({
      world: useWorldQuery("w1", { enabled: true }),
      places: useWorldPlacesQuery("w1", { enabled: true }),
      npcs: useWorldNpcsQuery("w1", { enabled: true }),
      factions: useWorldFactionsQuery("w1", { enabled: true }),
      items: useWorldItemsQuery("w1", { enabled: true }),
      inventory: useWorldInventoryQuery("w1", { enabled: true }),
      relationships: useWorldRelationshipsQuery("w1", { enabled: true }),
    }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(7));
    const urls = fetchSpy.mock.calls.map((c) => c[0].toString());
    expect(urls.some((u) => u.endsWith("/worlds/w1"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/worlds/w1/places"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/worlds/w1/npcs"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/worlds/w1/factions"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/worlds/w1/items"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/worlds/w1/npc-inventory"))).toBe(true);
    expect(urls.some((u) => u.endsWith("/worlds/w1/relationships"))).toBe(true);
  });

  it("does not fetch sub-resources when enabled is false", async () => {
    const { result } = renderHookWithClient(() => ({
      places: useWorldPlacesQuery("w1", { enabled: false }),
      npcs: useWorldNpcsQuery("w1", { enabled: false }),
    }));

    expect(result.current.places.isFetching).toBe(false);
    expect(result.current.npcs.isFetching).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("useWorldLoreQuery is dependent: it does not fire without an entityType", async () => {
    fetchSpy.mockResolvedValue(mockJson({ content: "old lore" }));

    const { result, rerender } = renderHookWithClient(
      ({ entityType }) =>
        useWorldLoreQuery({
          worldId: "w1",
          entityType,
          entityId: "region",
          enabled: true,
        }),
      { initialProps: { entityType: "" } },
    );

    expect(result.current.isFetching).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();

    rerender({ entityType: "places" });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    const url = fetchUrl(fetchSpy);
    expect(url).toContain("/worlds/w1/lore/places/region");
  });

  it("useDeleteWorldMutation DELETEs the world, removes the world query, and invalidates the list", async () => {
    fetchSpy.mockImplementation(async (url, init) => {
      const u = url.toString();
      if (init?.method === "DELETE" && u.endsWith("/worlds/w1")) {
        return new Response(null, { status: 204 });
      }
      if (u.endsWith("/worlds/w1")) {
        return mockJson({ world: { id: "w1", title: "W" } });
      }
      throw new Error(`Unmocked URL: ${u}`);
    });

    const { result, client } = renderHookWithClient(() => ({
      world: useWorldQuery("w1", { enabled: true }),
      del: useDeleteWorldMutation(),
    }));

    await waitFor(() => expect(client.getQueryData(queryKeys.world("w1"))).not.toBeUndefined());
    client.setQueryData(queryKeys.worlds, []);

    await act(async () => {
      await result.current.del.mutateAsync("w1");
    });

    const url = fetchUrl(fetchSpy, 1);
    expect(url).toContain("/worlds/w1");
    expect(fetchOptions(fetchSpy, 1).method).toBe("DELETE");
    expect(client.getQueryData(queryKeys.world("w1"))).toBeUndefined();
    const list = client.getQueryCache().find({ queryKey: queryKeys.worlds });
    expect(list?.state.isInvalidated).toBe(true);
  });
});
