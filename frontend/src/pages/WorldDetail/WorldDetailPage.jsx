import React, { useMemo, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Play, Trash2 } from "lucide-react";
import { cx } from "../../shared/lib/classNames.js";
import { markdownComponents } from "../../shared/markdown.jsx";
import {
  button,
  buttonDanger,
  buttonSecondary,
  h1,
  headerActions,
  label,
  muted,
  panel,
} from "../../shared/ui/classes.js";
import {
  useWorldQuery,
  useWorldPlacesQuery,
  useWorldNpcsQuery,
  useWorldFactionsQuery,
  useWorldItemsQuery,
  useWorldInventoryQuery,
  useWorldRelationshipsQuery,
  useWorldLoreQuery,
  useDeleteWorldMutation,
} from "./hooks/useWorldDetailQuery.js";
import DataTable from "./components/DataTable.jsx";
import ItemCarriers from "./components/ItemCarriers.jsx";
import LorePanel from "./components/LorePanel.jsx";
import PlaceMap from "./components/PlaceMap.jsx";

const tabsList = ["overview", "places", "npcs", "factions", "items", "relationships", "lore"];
const splitClass = "grid items-start gap-3.5 lg:grid-cols-[minmax(0,1fr)_360px]";
const tabClass = "border-0 border-b-2 border-transparent bg-transparent px-3 py-2.5 text-[#aaa49a]";
const tabActiveClass = "border-b-[#b98241] text-[#eeeeec]";
const summaryGridClass = "grid grid-cols-1 gap-4 border-b border-[#2e2e2c] p-4 lg:grid-cols-3";
const paragraphClass = "mt-2 leading-[1.55]";
const loreFullClass = "rounded-lg border border-[#2e2e2c] bg-[#171716] p-[18px]";

const INITIAL_TAB = "overview";
const INITIAL_SELECTED_ENTITY = { type: "region", row: { id: "region" } };

export default function WorldDetailPage({
  worldId,
  setError,
  onPlay,
  onAfterDelete,
}) {
  const enabled = !!worldId;
  const { data: world, isLoading: worldLoading } = useWorldQuery(worldId, { enabled });
  const { data: places = [] } = useWorldPlacesQuery(worldId, { enabled });
  const { data: npcs = [] } = useWorldNpcsQuery(worldId, { enabled });
  const { data: factions = [] } = useWorldFactionsQuery(worldId, { enabled });
  const { data: items = [] } = useWorldItemsQuery(worldId, { enabled });
  const { data: inventory = [] } = useWorldInventoryQuery(worldId, { enabled });
  const { data: relationships = [] } = useWorldRelationshipsQuery(worldId, { enabled });
  const deleteMut = useDeleteWorldMutation();

  const [activeTab, setActiveTab] = useState(INITIAL_TAB);
  const [selectedEntity, setSelectedEntity] = useState(INITIAL_SELECTED_ENTITY);

  React.useEffect(() => {
    setActiveTab(INITIAL_TAB);
    setSelectedEntity(INITIAL_SELECTED_ENTITY);
  }, [worldId]);

  const loreEntityType = selectedEntity?.type ?? "region";
  const loreEntityId = selectedEntity?.row?.id ?? "region";
  const { data: lore = "", isLoading: loreLoading } = useWorldLoreQuery({
    worldId,
    entityType: loreEntityType,
    entityId: loreEntityId,
    enabled: enabled && !!selectedEntity?.type,
  });

  const selectedPlace = selectedEntity?.type === "places" ? selectedEntity.row : places[0];
  const selectedItem = selectedEntity?.type === "items" || selectedEntity?.type === "staple-items"
    ? selectedEntity.row
    : items[0];
  const placeById = useMemo(() => new Map(places.map((place) => [place.id, place])), [places]);
  const npcsWithLocation = useMemo(
    () => npcs.map((npc) => {
      const place = placeById.get(npc.current_place_id) || placeById.get(npc.home_place_id);
      return { ...npc, location: place?.name || "Unknown location" };
    }),
    [npcs, placeById],
  );

  const handleDelete = () => {
    if (!worldId) return;
    if (!window.confirm(`Delete "${world?.title ?? worldId}"?`)) return;
    deleteMut.mutate(worldId, {
      onSuccess: () => onAfterDelete?.(),
      onError: (deleteError) => setError(deleteError.message),
    });
  };

  if (!world) {
    return (
      <main className="min-w-0 bg-[#111111] p-6">
        <div className="mb-[18px] flex items-start justify-between gap-4">
          <h1 className={h1}>World</h1>
        </div>
        <div className="p-3.5 text-[13px] text-[#aaa49a]">Loading world...</div>
      </main>
    );
  }

  return (
    <main className="min-w-0 bg-[#111111] p-6">
      <div className="mb-[18px] flex items-start justify-between gap-4">
        <div>
          <h1 className={h1}>{world.title}</h1>
          <div className={muted}>{world.region?.name} - {world.provider}/{world.model_name}</div>
        </div>
        <div className={headerActions}>
          <button className={cx(button, buttonSecondary)} onClick={onPlay}>
            <Play size={16} />
            Play
          </button>
          <button
            className={cx(button, buttonDanger)}
            onClick={handleDelete}
          >
            <Trash2 size={16} />
            Delete
          </button>
        </div>
      </div>

      <nav className="mb-3.5 flex gap-0.5 border-b border-[#2e2e2c]">
        {tabsList.map((tab) => (
          <button
            key={tab}
            className={cx(tabClass, activeTab === tab && tabActiveClass)}
            onClick={() => {
              setActiveTab(tab);
              if (tab === "items" && items[0] && selectedEntity?.type !== "items" && selectedEntity?.type !== "staple-items") {
                setSelectedEntity({ type: items[0].lore_entity_type, row: items[0] });
              }
            }}
          >
            {tab}
          </button>
        ))}
      </nav>

      {activeTab === "overview" ? (
        <section className={splitClass}>
          <div className={panel}>
            <div className={summaryGridClass}>
              <div>
                <div className={label}>Summary</div>
                <p className={paragraphClass}>{world.region?.summary}</p>
              </div>
              <div>
                <div className={label}>Climate</div>
                <p className={paragraphClass}>{world.region?.climate}</p>
              </div>
              <div>
                <div className={label}>Danger profile</div>
                <p className={paragraphClass}>{world.region?.danger_profile}</p>
              </div>
            </div>
            <PlaceMap places={places} selectedId={selectedPlace?.id} onSelect={(row) => {
              setSelectedEntity({ type: "places", row });
              setActiveTab("places");
            }} />
          </div>
          <LorePanel lore={lore} loading={loreLoading} />
        </section>
      ) : null}

      {activeTab === "places" ? (
        <section className={splitClass}>
          <div className={panel}>
            <DataTable
              rows={places}
              selectedId={selectedEntity?.row?.id}
              onRowClick={(row) => setSelectedEntity({ type: "places", row })}
              columns={[
                { key: "name", label: "Name" },
                { key: "place_type", label: "Type" },
                { key: "terrain", label: "Terrain" },
                { key: "danger_level", label: "Danger" },
                { key: "population_estimate", label: "Population" },
              ]}
            />
          </div>
          <LorePanel lore={lore} loading={loreLoading} />
        </section>
      ) : null}

      {activeTab === "npcs" ? (
        <section className={splitClass}>
          <div className={panel}>
            <DataTable
              rows={npcsWithLocation}
              selectedId={selectedEntity?.row?.id}
              onRowClick={(row) => setSelectedEntity({ type: "npcs", row })}
              columns={[
                { key: "name", label: "Name" },
                { key: "location", label: "Location" },
                { key: "age", label: "Age" },
                { key: "job", label: "Job" },
                { key: "personality", label: "Personality", render: (npc) => (Array.isArray(npc.personality) ? npc.personality.join(", ") : npc.personality) },
                { key: "status", label: "Status" },
              ]}
            />
          </div>
          <LorePanel lore={lore} loading={loreLoading} />
        </section>
      ) : null}

      {activeTab === "factions" ? (
        <section className={splitClass}>
          <div className={panel}>
            <DataTable
              rows={factions}
              selectedId={selectedEntity?.row?.id}
              onRowClick={(row) => setSelectedEntity({ type: "factions", row })}
              columns={[
                { key: "name", label: "Name" },
                { key: "type", label: "Type" },
                { key: "goals", label: "Goals" },
                { key: "public_reputation", label: "Reputation" },
                { key: "power_level", label: "Power" },
              ]}
            />
          </div>
          <LorePanel lore={lore} loading={loreLoading} />
        </section>
      ) : null}

      {activeTab === "items" ? (
        <section className={splitClass}>
          <div className={panel}>
            <DataTable
              rows={items}
              selectedId={selectedItem?.id}
              onRowClick={(row) => setSelectedEntity({ type: row.lore_entity_type, row })}
              columns={[
                { key: "name", label: "Name" },
                { key: "category", label: "Category" },
                { key: "rarity", label: "Rarity" },
                { key: "source_type", label: "Source" },
                { key: "effect_summary", label: "Effect" },
                { key: "total_quantity", label: "Qty" },
              ]}
            />
            <ItemCarriers item={selectedItem} />
          </div>
          <LorePanel lore={lore} loading={loreLoading} />
        </section>
      ) : null}

      {activeTab === "relationships" ? (
        <section className={panel}>
          <DataTable
            rows={relationships}
            columns={[
              { key: "source_type", label: "Source type" },
              { key: "source_id", label: "Source" },
              { key: "relation_type", label: "Relation" },
              { key: "target_type", label: "Target type" },
              { key: "target_id", label: "Target" },
              { key: "description", label: "Description" },
            ]}
          />
        </section>
      ) : null}

      {activeTab === "lore" ? (
        <section className={loreFullClass}>
          <ReactMarkdown components={markdownComponents}>{lore || "Select a place, NPC, faction, item, or overview region first."}</ReactMarkdown>
        </section>
      ) : null}
    </main>
  );
}
