import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../api/client.js";
import { queryKeys } from "../../api/queryKeys.js";

export function useModelsCatalog() {
  return useQuery({
    queryKey: queryKeys.models,
    queryFn: async () => {
      const payload = await request("/models");
      return payload.models ?? [];
    },
  });
}

export function useActiveModel() {
  return useQuery({
    queryKey: queryKeys.activeModel,
    queryFn: () => request("/models/active"),
  });
}

export function useSelectModelMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (modelId) =>
      request("/models/active", {
        method: "PUT",
        body: JSON.stringify({ model_id: modelId }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.activeModel }),
  });
}

export function useTestModelMutation() {
  return useMutation({
    mutationFn: (model) =>
      request("/models/test", {
        method: "POST",
        body: JSON.stringify({ models: [model] }),
      }),
  });
}
