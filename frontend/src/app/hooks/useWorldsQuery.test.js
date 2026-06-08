import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { waitFor } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, mockJson } from "../../test-utils/renderHook.jsx";
import { useWorldsQuery, useInvalidateWorlds } from "./useWorldsQuery.js";

describe("useWorldsQuery", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("fetches /worlds and returns the worlds array", async () => {
    fetchSpy.mockResolvedValue(
      mockJson({ worlds: [{ id: "w1", title: "First" }, { id: "w2", title: "Second" }] }),
    );

    const { result } = renderHookWithClient(() => useWorldsQuery());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([
      { id: "w1", title: "First" },
      { id: "w2", title: "Second" },
    ]);
    expect(fetchSpy).toHaveBeenCalledTimes(1);
    expect(fetchUrl(fetchSpy)).toContain("/worlds");
  });

  it("returns an empty array when the worlds key is missing", async () => {
    fetchSpy.mockResolvedValue(mockJson({}));

    const { result } = renderHookWithClient(() => useWorldsQuery());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([]);
  });

  it("useInvalidateWorlds re-fetches the worlds list", async () => {
    fetchSpy.mockResolvedValue(mockJson({ worlds: [] }));

    const { result, client } = renderHookWithClient(() => ({
      invalidate: useInvalidateWorlds(),
      query: useWorldsQuery(),
    }));

    await waitFor(() => expect(result.current.query.isSuccess).toBe(true));
    expect(fetchSpy).toHaveBeenCalledTimes(1);

    result.current.invalidate();

    await waitFor(() => expect(fetchSpy).toHaveBeenCalledTimes(2));
    expect(client.getQueryData(["worlds"])).toEqual([]);
  });
});
