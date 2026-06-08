import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../../api/client.js";
import { queryKeys } from "../../../api/queryKeys.js";

export function usePlayStateQuery({ worldId, enabled }) {
  return useQuery({
    queryKey: queryKeys.playState(worldId),
    queryFn: () => request(`/worlds/${encodeURIComponent(worldId)}/play`),
    enabled: enabled && !!worldId,
  });
}

export function usePlayInputMutation({ worldId }) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input) => {
      if (!worldId) throw new Error("Missing world id.");
      return request(`/worlds/${encodeURIComponent(worldId)}/play/input`, {
        method: "POST",
        body: JSON.stringify({ input }),
      });
    },
    onSuccess: (payload) => {
      qc.setQueryData(queryKeys.playState(worldId), payload);
    },
    onError: () => {
      qc.invalidateQueries({ queryKey: queryKeys.playState(worldId) });
    },
  });
}
