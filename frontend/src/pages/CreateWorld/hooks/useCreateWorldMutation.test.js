import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, fetchOptions, mockJson } from "../../../test-utils/renderHook.jsx";
import { queryKeys } from "../../../api/queryKeys.js";
import { useCreateWorldMutation } from "./useCreateWorldMutation.js";

describe("useCreateWorldMutation", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("POSTs to /worlds with the prompt and model_id, and invalidates the worlds list on success", async () => {
    fetchSpy.mockResolvedValue(mockJson({ id: "w-new" }));

    const { result, client } = renderHookWithClient(() => ({
      create: useCreateWorldMutation(),
    }));

    client.setQueryData(queryKeys.worlds, []);

    await act(async () => {
      await result.current.create.mutateAsync({ prompt: "rainy frontier", modelId: "m1" });
    });

    expect(fetchUrl(fetchSpy)).toContain("/worlds");
    expect(fetchOptions(fetchSpy).method).toBe("POST");
    expect(JSON.parse(fetchOptions(fetchSpy).body)).toEqual({
      prompt: "rainy frontier",
      model_id: "m1",
    });

    const list = client.getQueryCache().find({ queryKey: queryKeys.worlds });
    expect(list?.state.isInvalidated).toBe(true);
  });
});
