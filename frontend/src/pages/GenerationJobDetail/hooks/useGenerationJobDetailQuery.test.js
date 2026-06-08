import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { waitFor, act } from "@testing-library/react";
import { renderHookWithClient, fetchUrl, fetchOptions, mockJson } from "../../../test-utils/renderHook.jsx";
import { queryKeys } from "../../../api/queryKeys.js";
import { POLL_INTERVAL_MS } from "../../../shared/lib/constants.js";
import {
  useGenerationJobQuery,
  useRestartJobMutation,
  useRetryStepMutation,
} from "./useGenerationJobDetailQuery.js";

describe("useGenerationJobDetailQuery", () => {
  let fetchSpy;

  beforeEach(() => {
    fetchSpy = vi.spyOn(global, "fetch");
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it("fetches the job by id and returns the job object", async () => {
    fetchSpy.mockResolvedValue(mockJson({ job: { id: "j1", status: "running" } }));

    const { result } = renderHookWithClient(() =>
      useGenerationJobQuery({ jobId: "j1", enabled: true }),
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual({ id: "j1", status: "running" });
    expect(fetchUrl(fetchSpy)).toContain("/generation-jobs/j1");
  });

  it("encodes special characters in the job id", async () => {
    fetchSpy.mockResolvedValue(mockJson({ job: { id: "job/with spaces" } }));

    renderHookWithClient(() => useGenerationJobQuery({ jobId: "job/with spaces", enabled: true }));

    await waitFor(() => expect(fetchSpy).toHaveBeenCalled());
    expect(fetchUrl(fetchSpy)).toContain("job%2Fwith%20spaces");
  });

  it("does not fetch when jobId is empty", async () => {
    const { result } = renderHookWithClient(() =>
      useGenerationJobQuery({ jobId: "", enabled: true }),
    );

    expect(result.current.isFetching).toBe(false);
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("configures the query with the POLL_INTERVAL_MS refetch interval", async () => {
    fetchSpy.mockResolvedValue(mockJson({ job: null }));

    const { client } = renderHookWithClient(() =>
      useGenerationJobQuery({ jobId: "j1", enabled: true }),
    );

    await waitFor(() => {
      const q = client.getQueryCache().find({ queryKey: queryKeys.generationJob("j1") });
      expect(q?.options.refetchInterval).toBe(POLL_INTERVAL_MS);
    });
  });

  it("useRestartJobMutation sets the job in cache and invalidates jobs + worlds", async () => {
    const updatedJob = { id: "j1", status: "pending" };
    fetchSpy.mockResolvedValue(mockJson({ job: updatedJob }));

    const { result, client } = renderHookWithClient(() => ({
      restart: useRestartJobMutation(),
    }));

    client.setQueryData(queryKeys.generationJobs, []);
    client.setQueryData(queryKeys.worlds, []);

    await act(async () => {
      await result.current.restart.mutateAsync({ jobId: "j1", modelId: "m1" });
    });

    expect(client.getQueryData(queryKeys.generationJob("j1"))).toEqual(updatedJob);
    const jobs = client.getQueryCache().find({ queryKey: queryKeys.generationJobs });
    const worlds = client.getQueryCache().find({ queryKey: queryKeys.worlds });
    expect(jobs?.state.isInvalidated).toBe(true);
    expect(worlds?.state.isInvalidated).toBe(true);
  });

  it("useRetryStepMutation encodes the step name in the URL", async () => {
    fetchSpy.mockResolvedValue(mockJson({ job: { id: "j1" } }));

    const { result } = renderHookWithClient(() => ({
      retry: useRetryStepMutation(),
    }));

    await act(async () => {
      await result.current.retry.mutateAsync({ jobId: "j1", stepName: "places batch", modelId: "m1" });
    });

    const url = fetchUrl(fetchSpy);
    expect(url).toContain("/generation-jobs/j1/steps/places%20batch/retry");
    expect(url).toContain("model_id=m1");
    expect(fetchOptions(fetchSpy).method).toBe("POST");
  });
});
