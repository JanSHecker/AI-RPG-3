import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { waitFor, act } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, fetchOptions, mockJson } from "../../test-utils/renderHook.jsx";
import {
  useModelsCatalog,
  useActiveModel,
  useSelectModelMutation,
  useTestModelMutation,
} from "./useModelsQuery.js";

describe("models queries and mutations", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("useModelsCatalog fetches /models and returns the models array", async () => {
    fetchSpy.mockResolvedValue(
      mockJson({ models: [{ id: "m1", label: "Model 1" }, { id: "m2", label: "Model 2" }] }),
    );

    const { result } = renderHookWithClient(() => useModelsCatalog());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
    expect(fetchUrl(fetchSpy)).toContain("/models");
  });

  it("useActiveModel fetches /models/active", async () => {
    fetchSpy.mockResolvedValue(mockJson({ id: "m1", label: "Model 1" }));

    const { result } = renderHookWithClient(() => useActiveModel());

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ id: "m1", label: "Model 1" });
    expect(fetchUrl(fetchSpy)).toContain("/models/active");
  });

  it("useSelectModelMutation PUTs to /models/active and invalidates the active query", async () => {
    fetchSpy.mockResolvedValue(mockJson({ id: "m2" }));

    const { result, client } = renderHookWithClient(() => ({
      select: useSelectModelMutation(),
    }));

    client.setQueryData(["models", "active"], { id: "m1" });

    await act(async () => {
      await result.current.select.mutateAsync("m2");
    });

    const call = fetchSpy.mock.calls[0];
    expect(fetchUrl(fetchSpy)).toContain("/models/active");
    expect(fetchOptions(fetchSpy).method).toBe("PUT");
    expect(JSON.parse(fetchOptions(fetchSpy).body)).toEqual({ model_id: "m2" });

    const queryCache = client.getQueryCache();
    const active = queryCache.find({ queryKey: ["models", "active"] });
    expect(active?.state.isInvalidated).toBe(true);
  });

  it("useTestModelMutation POSTs to /models/test and returns the result", async () => {
    fetchSpy.mockResolvedValue(
      mockJson({ results: [{ ok: true, latency_ms: 42, response_preview: "hi" }] }),
    );

    const { result } = renderHookWithClient(() => ({
      test: useTestModelMutation(),
    }));

    let returned;
    await act(async () => {
      returned = await result.current.test.mutateAsync({ id: "m1", label: "Model 1" });
    });

    expect(fetchUrl(fetchSpy)).toContain("/models/test");
    expect(fetchOptions(fetchSpy).method).toBe("POST");
    expect(JSON.parse(fetchOptions(fetchSpy).body)).toEqual({ models: [{ id: "m1", label: "Model 1" }] });
    expect(returned).toEqual({ results: [{ ok: true, latency_ms: 42, response_preview: "hi" }] });
  });
});
