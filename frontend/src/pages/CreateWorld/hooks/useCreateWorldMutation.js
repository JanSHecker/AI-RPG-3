import { useMutation, useQueryClient } from "@tanstack/react-query";
import { request } from "../../../api/client.js";
import { queryKeys } from "../../../api/queryKeys.js";

export function useCreateWorldMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ prompt, modelId }) =>
      request("/worlds", {
        method: "POST",
        body: JSON.stringify({ prompt, model_id: modelId }),
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: queryKeys.worlds }),
  });
}
