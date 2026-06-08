import { useCallback, useEffect, useState } from "react";
import { request } from "../../../api/client.js";

const initialData = { places: [], npcs: [], factions: [], items: [], inventory: [], relationships: [] };

export function useWorldDetailPage({ worldId, setError, onAfterDelete, onWorldsChanged }) {
  const [world, setWorld] = useState(null);
  const [data, setData] = useState(initialData);
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedEntity, setSelectedEntity] = useState({ type: "region", row: { id: "region" } });
  const [lore, setLore] = useState("");
  const [loreLoading, setLoreLoading] = useState(false);

  const loadWorld = useCallback(async (targetWorldId) => {
    const id = targetWorldId || worldId;
    if (!id) return null;
    const [
      worldPayload,
      placesPayload,
      npcsPayload,
      factionsPayload,
      itemsPayload,
      inventoryPayload,
      relationshipsPayload,
    ] = await Promise.all([
      request(`/worlds/${encodeURIComponent(id)}`),
      request(`/worlds/${encodeURIComponent(id)}/places`),
      request(`/worlds/${encodeURIComponent(id)}/npcs`),
      request(`/worlds/${encodeURIComponent(id)}/factions`),
      request(`/worlds/${encodeURIComponent(id)}/items`),
      request(`/worlds/${encodeURIComponent(id)}/npc-inventory`),
      request(`/worlds/${encodeURIComponent(id)}/relationships`),
    ]);
    setWorld(worldPayload.world);
    setData({
      places: placesPayload.places ?? [],
      npcs: npcsPayload.npcs ?? [],
      factions: factionsPayload.factions ?? [],
      items: itemsPayload.items ?? [],
      inventory: inventoryPayload.inventory ?? [],
      relationships: relationshipsPayload.relationships ?? [],
    });
    setActiveTab("overview");
    setSelectedEntity({ type: "region", row: { id: "region" } });
    return worldPayload.world;
  }, [worldId]);

  useEffect(() => {
    if (!worldId) {
      setWorld(null);
      setData(initialData);
      return;
    }
    loadWorld(worldId).catch((loadError) => setError(loadError.message));
  }, [worldId, loadWorld, setError]);

  useEffect(() => {
    if (!worldId || !selectedEntity?.type) {
      setLore("");
      return;
    }
    const entityType = selectedEntity.type;
    const entityId = selectedEntity.row?.id ?? "region";
    setLoreLoading(true);
    request(`/worlds/${encodeURIComponent(worldId)}/lore/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)
      .then((payload) => setLore(payload.content ?? ""))
      .catch(() => setLore(""))
      .finally(() => setLoreLoading(false));
  }, [worldId, selectedEntity]);

  const deleteSelectedWorld = async () => {
    if (!worldId) return;
    const confirmed = window.confirm(`Delete "${world?.title ?? worldId}"?`);
    if (!confirmed) return;
    await request(`/worlds/${encodeURIComponent(worldId)}`, { method: "DELETE" });
    if (onAfterDelete) await onAfterDelete();
    if (onWorldsChanged) await onWorldsChanged();
  };

  return {
    world,
    data,
    activeTab,
    setActiveTab,
    selectedEntity,
    setSelectedEntity,
    lore,
    loreLoading,
    deleteSelectedWorld,
  };
}
