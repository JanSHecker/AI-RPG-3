import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { request } from "../../../api/client.js";
import { queryKeys } from "../../../api/queryKeys.js";

export function useWorldQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.world(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}`);
      return payload.world ?? null;
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldPlacesQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.worldPlaces(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/places`);
      return payload.places ?? [];
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldNpcsQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.worldNpcs(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/npcs`);
      return payload.npcs ?? [];
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldFactionsQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.worldFactions(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/factions`);
      return payload.factions ?? [];
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldItemsQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.worldItems(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/items`);
      return payload.items ?? [];
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldInventoryQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.worldInventory(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/npc-inventory`);
      return payload.inventory ?? [];
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldRelationshipsQuery(worldId, { enabled }) {
  return useQuery({
    queryKey: queryKeys.worldRelationships(worldId),
    queryFn: async () => {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/relationships`);
      return payload.relationships ?? [];
    },
    enabled: enabled && !!worldId,
  });
}

export function useWorldLoreQuery({ worldId, entityType, entityId, enabled }) {
  return useQuery({
    queryKey: queryKeys.worldLore(worldId, entityType, entityId),
    queryFn: async () => {
      const payload = await request(
        `/worlds/${encodeURIComponent(worldId)}/lore/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
      );
      return payload.content ?? "";
    },
    enabled: enabled && !!worldId && !!entityType,
  });
}

export function useDeleteWorldMutation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (worldId) => {
      if (!worldId) throw new Error("Missing world id.");
      return request(`/worlds/${encodeURIComponent(worldId)}`, { method: "DELETE" });
    },
    onSuccess: (_data, worldId) => {
      qc.removeQueries({ queryKey: queryKeys.world(worldId) });
      qc.invalidateQueries({ queryKey: queryKeys.worlds });
    },
  });
}
