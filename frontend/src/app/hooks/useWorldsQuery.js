import { useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../api/client.js";
import { queryKeys } from "../../api/queryKeys.js";

export function useWorldsQuery() {
  return useQuery({
    queryKey: queryKeys.worlds,
    queryFn: async () => {
      const payload = await request("/worlds");
      return payload.worlds ?? [];
    },
  });
}

export function useInvalidateWorlds() {
  const qc = useQueryClient();
  return () => qc.invalidateQueries({ queryKey: queryKeys.worlds });
}
