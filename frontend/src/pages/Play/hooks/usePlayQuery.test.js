import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { waitFor, act } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, fetchOptions, mockJson } from "../../../test-utils/renderHook.jsx";
import { queryKeys } from "../../../api/queryKeys.js";
import { usePlayStateQuery, usePlayInputMutation } from "./usePlayQuery.js";

describe("usePlayQuery", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("usePlayStateQuery fetches /worlds/{id}/play", async () => {
    fetchSpy.mockResolvedValue(mockJson({ world: { id: "w1" }, messages: [] }));

    const { result } = renderHookWithClient(() =>
      usePlayStateQuery({ worldId: "w1", enabled: true }),
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ world: { id: "w1" }, messages: [] });
    expect(fetchUrl(fetchSpy)).toContain("/worlds/w1/play");
  });

  it("usePlayInputMutation POSTs to /worlds/{id}/play/input and writes the response into the play state cache", async () => {
    const nextState = { world: { id: "w1" }, messages: [{ id: "m1" }] };
    fetchSpy.mockResolvedValue(mockJson(nextState));

    const { result, client } = renderHookWithClient(() => ({
      input: usePlayInputMutation({ worldId: "w1" }),
    }));

    await act(async () => {
      await result.current.input.mutateAsync("look around");
    });

    const url = fetchUrl(fetchSpy);
    expect(url).toContain("/worlds/w1/play/input");
    expect(fetchOptions(fetchSpy).method).toBe("POST");
    expect(JSON.parse(fetchOptions(fetchSpy).body)).toEqual({ input: "look around" });
    expect(client.getQueryData(queryKeys.playState("w1"))).toEqual(nextState);
  });

  it("usePlayInputMutation invalidates the play state query on error (so the next render refetches)", async () => {
    fetchSpy.mockResolvedValue(mockJson({ detail: "boom" }, { status: 500 }));

    const { result, client } = renderHookWithClient(() => ({
      input: usePlayInputMutation({ worldId: "w1" }),
    }));

    client.setQueryData(queryKeys.playState("w1"), { messages: [] });

    await act(async () => {
      try {
        await result.current.input.mutateAsync("x");
      } catch {
        // expected
      }
    });

    const q = client.getQueryCache().find({ queryKey: queryKeys.playState("w1") });
    expect(q?.state.isInvalidated).toBe(true);
  });
});
