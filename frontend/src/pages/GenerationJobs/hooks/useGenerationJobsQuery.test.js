import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { waitFor, act } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, fetchOptions, mockJson } from "../../../test-utils/renderHook.jsx";
import { queryKeys } from "../../../api/queryKeys.js";
import { POLL_INTERVAL_MS } from "../../../shared/lib/constants.js";
import {
  useGenerationJobsQuery,
  useClearFinishedJobsMutation,
  useClearActiveJobsMutation,
  useRestartJobMutation,
} from "./useGenerationJobsQuery.js";

describe("useGenerationJobsQuery", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("fetches /generation-jobs and returns the jobs array", async () => {
    fetchSpy.mockResolvedValue(mockJson({ jobs: [{ id: "j1", status: "done" }] }));

    const { result } = renderHookWithClient(() => useGenerationJobsQuery({ enabled: true }));

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual([{ id: "j1", status: "done" }]);
    expect(fetchUrl(fetchSpy)).toContain("/generation-jobs");
  });

  it("configures the query with the POLL_INTERVAL_MS refetch interval", async () => {
    fetchSpy.mockResolvedValue(mockJson({ jobs: [] }));

    const { client } = renderHookWithClient(() => useGenerationJobsQuery({ enabled: true }));

    await waitFor(() => {
      const q = client.getQueryCache().find({ queryKey: queryKeys.generationJobs });
      expect(q?.options.refetchInterval).toBe(POLL_INTERVAL_MS);
    });
  });

  it("does not fetch when enabled is false", async () => {
    const { result } = renderHookWithClient(() => useGenerationJobsQuery({ enabled: false }));

    expect(result.current.isFetching).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("useClearFinishedJobsMutation DELETEs /generation-jobs/finished and invalidates jobs", async () => {
    fetchSpy.mockResolvedValue(mockJson({ jobs: [] }));

    const { result, client } = renderHookWithClient(() => ({
      clear: useClearFinishedJobsMutation(),
    }));

    client.setQueryData(queryKeys.generationJobs, []);

    await act(async () => {
      await result.current.clear.mutateAsync();
    });

    expect(fetchUrl(fetchSpy)).toContain("/generation-jobs/finished");
    expect(fetchOptions(fetchSpy).method).toBe("DELETE");
    const q = client.getQueryCache().find({ queryKey: queryKeys.generationJobs });
    expect(q?.state.isInvalidated).toBe(true);
  });

  it("useClearActiveJobsMutation invalidates BOTH jobs and worlds", async () => {
    fetchSpy.mockResolvedValue(mockJson({ jobs: [] }));

    const { result, client } = renderHookWithClient(() => ({
      clear: useClearActiveJobsMutation(),
    }));

    client.setQueryData(queryKeys.generationJobs, []);
    client.setQueryData(queryKeys.worlds, []);

    await act(async () => {
      await result.current.clear.mutateAsync();
    });

    const jobs = client.getQueryCache().find({ queryKey: queryKeys.generationJobs });
    const worlds = client.getQueryCache().find({ queryKey: queryKeys.worlds });
    expect(jobs?.state.isInvalidated).toBe(true);
    expect(worlds?.state.isInvalidated).toBe(true);
  });

  it("useRestartJobMutation POSTs to restart with model_id query param and body, then invalidates jobs", async () => {
    fetchSpy.mockResolvedValue(mockJson({ job: { id: "j1", status: "pending" } }));

    const { result, client } = renderHookWithClient(() => ({
      restart: useRestartJobMutation(),
    }));

    client.setQueryData(queryKeys.generationJobs, []);

    await act(async () => {
      await result.current.restart.mutateAsync({ jobId: "j1", modelId: "m1" });
    });

    const url = fetchUrl(fetchSpy);
    expect(url).toContain("/generation-jobs/j1/restart");
    expect(url).toContain("model_id=m1");
    expect(fetchOptions(fetchSpy).method).toBe("POST");
    expect(JSON.parse(fetchOptions(fetchSpy).body)).toEqual({ model_id: "m1" });
    const q = client.getQueryCache().find({ queryKey: queryKeys.generationJobs });
    expect(q?.state.isInvalidated).toBe(true);
  });

  it("useRestartJobMutation throws when no model is selected", async () => {
    const { result } = renderHookWithClient(() => ({
      restart: useRestartJobMutation(),
    }));

    await act(async () => {
      await expect(result.current.restart.mutateAsync({ jobId: "j1", modelId: "" })).rejects.toThrow(
        /Select a model/,
      );
    });
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
