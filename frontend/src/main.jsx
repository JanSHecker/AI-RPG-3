import React, { useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import ReactMarkdown from "react-markdown";
import { flexRender, getCoreRowModel, getSortedRowModel, useReactTable } from "@tanstack/react-table";
import { ArrowLeft, Check, ChevronRight, ExternalLink, ListChecks, MapPin, Plus, RefreshCw, RotateCcw, Trash2 } from "lucide-react";
import "./styles.css";

const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

async function request(path, options = {}) {
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers ?? {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `Request failed with ${response.status}`;
    try {
      const payload = await response.json();
      detail = payload.detail || detail;
    } catch {
      // Keep fallback detail.
    }
    throw new Error(detail);
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

function formatDate(value) {
  if (!value) return "";
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function Sidebar({
  worlds,
  selectedWorldId,
  onSelectWorld,
  onNewWorld,
  onShowJobs,
  onRefresh,
  models,
  activeModelId,
  onSelectModel,
  onTestModel,
  modelStatus,
  modelTestResult,
}) {
  const modelStatusText = {
    idle: "Waiting to test selected model.",
    testing: "Waiting for the model response...",
    ok: `Model responded successfully${modelTestResult?.latency_ms != null ? ` in ${modelTestResult.latency_ms} ms` : ""}.`,
    failed: "Model test failed.",
  }[modelStatus] ?? "Waiting to test selected model.";
  const modelError = modelStatus === "failed" ? modelTestResult?.error : "";
  const modelPreview = modelStatus === "ok" ? modelTestResult?.response_preview : "";

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-title">World Data</div>
        <div className="brand-subtitle">Text RPG generator</div>
      </div>

      <div className="sidebar-actions">
        <button className="button primary" onClick={onNewWorld}>
          <Plus size={16} />
          New world
        </button>
        <button className="icon-button" onClick={onShowJobs} title="Generation jobs">
          <ListChecks size={16} />
        </button>
        <button className="icon-button" onClick={onRefresh} title="Refresh worlds">
          <RefreshCw size={16} />
        </button>
      </div>

      <div className="sidebar-section">
        <label className="field-label" htmlFor="model-select">Model</label>
        <select id="model-select" value={activeModelId || ""} onChange={(event) => onSelectModel(event.target.value)}>
          {models.map((model) => (
            <option key={model.id} value={model.id}>
              {model.label}
            </option>
          ))}
        </select>
        <button className="button secondary full" onClick={onTestModel} disabled={!activeModelId || modelStatus === "testing"}>
          {modelStatus === "testing" ? <RefreshCw size={16} /> : <Check size={16} />}
          {modelStatus === "testing" ? "Testing" : "Test model"}
        </button>
        <div className={`model-test-feedback model-test-${modelStatus}`} aria-live="polite">
          <div className="model-test-status">{modelStatusText}</div>
          {modelError ? <div className="model-test-error">{modelError}</div> : null}
          {modelPreview ? <div className="model-test-preview">Response: {modelPreview}</div> : null}
        </div>
      </div>

      <div className="world-list">
        {worlds.length === 0 ? (
          <div className="empty-list">No worlds yet.</div>
        ) : (
          worlds.map((world) => (
            <button
              key={world.id}
              className={`world-row ${selectedWorldId === world.id ? "selected" : ""}`}
              onClick={() => onSelectWorld(world.id)}
            >
              <span className="world-title">{world.title}</span>
              <span className="world-meta">{world.provider} · {formatDate(world.updated_at)}</span>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}

function CreateWorld({ prompt, setPrompt, onSubmit, creating, error }) {
  return (
    <main className="content">
      <div className="content-header">
        <h1>Create world</h1>
      </div>
      <section className="editor-panel">
        <label className="field-label" htmlFor="prompt">World prompt</label>
        <textarea
          id="prompt"
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="A rain-beaten frontier around an old imperial road, with fortress politics, hungry forests, and towns that owe debts to the wrong people."
          rows={8}
        />
        <div className="form-row">
          <button className="button primary" onClick={onSubmit} disabled={creating || !prompt.trim()}>
            {creating ? <RefreshCw size={16} /> : <Plus size={16} />}
            {creating ? "Queueing" : "Generate world"}
          </button>
          {error ? <span className="error-text">{error}</span> : null}
        </div>
      </section>
    </main>
  );
}

function statusLabel(status) {
  if (!status) return "pending";
  return status.charAt(0).toUpperCase() + status.slice(1);
}

function routeFromPath() {
  const jobDetailMatch = window.location.pathname.match(/^\/jobs\/([^/]+)$/);
  if (jobDetailMatch) {
    return { mode: "job-detail", jobId: decodeURIComponent(jobDetailMatch[1]) };
  }
  if (window.location.pathname === "/jobs") {
    return { mode: "jobs", jobId: "" };
  }
  return { mode: "create", jobId: "" };
}

function generatorInstanceNote(step) {
  if (step.latency_ms) return `${step.latency_ms} ms`;
  if (step.started_at) return `Started ${formatDate(step.started_at)}`;
  if (step.finished_at) return `Finished ${formatDate(step.finished_at)}`;
  return "Waiting";
}

function generatorGroupType(step, index) {
  const type = step.step_name || `step-${index}`;
  if (type.startsWith("places_")) return "villages_places";
  if (type.startsWith("npcs_")) return "npcs";
  return type;
}

function generatorGroupLabel(type, step) {
  if (type === "villages_places") return "Villages & Places";
  if (type === "npcs") return "NPCs";
  return step.label || type;
}

function generatorCardTitle(instance, row) {
  if (instance.step_name === row.type && row.instances.length > 1) return "Overall";
  if (instance.step_name?.startsWith("places_")) return instance.label || "Places batch";
  if (instance.step_name?.startsWith("npcs_")) return instance.label || "NPC batch";
  return "";
}

function groupGeneratorInstances(steps = []) {
  const activeStatuses = new Set(["pending", "running", "retrying"]);
  const rowsByType = new Map();

  steps.forEach((step, index) => {
    const type = generatorGroupType(step, index);
    const existing = rowsByType.get(type) ?? {
      type,
      label: generatorGroupLabel(type, step),
      activeCount: 0,
      instances: [],
    };
    if (hasVisibleGeneratorProgress(step) && activeStatuses.has(step.status)) {
      existing.activeCount += 1;
    }
    if (hasVisibleGeneratorProgress(step)) {
      existing.instances.push({ ...step, instanceId: step.id || `${type}-${index}` });
    }
    rowsByType.set(type, existing);
  });

  return Array.from(rowsByType.values());
}

function hasVisibleGeneratorProgress(step) {
  if (!step) return false;
  if (step.status && step.status !== "pending") return true;
  if (Number(step.attempts || 0) > 0) return true;
  return Boolean(step.error || step.raw_response || step.parsed_payload || step.started_at || step.finished_at);
}

function GenerationJobs({ jobs, loading, error, onRefresh, onSelectJob, onOpenWorld, onRestartJob, onClearFinished, onClearActive }) {
  const activeCount = jobs.filter((job) => ["pending", "running", "retrying"].includes(job.status)).length;
  const finishedCount = jobs.filter((job) => ["done", "failed"].includes(job.status)).length;

  return (
    <main className="content jobs-content">
      <div className="jobs-wrap">
        <div className="content-header">
          <div>
            <h1>Generation jobs</h1>
            <div className="muted">{loading ? "Refreshing..." : `${jobs.length} visible`}</div>
          </div>
          <div className="header-actions">
            <button className="button secondary" onClick={onClearFinished} disabled={finishedCount === 0}>
              <Trash2 size={16} />
              Clear old
            </button>
            <button className="button danger" onClick={onClearActive} disabled={activeCount === 0}>
              <Trash2 size={16} />
              Clear running
            </button>
            <button className="button secondary" onClick={onRefresh}>
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}

        <section className="job-list-panel">
          {jobs.length === 0 ? (
            <div className="empty-panel">No generation jobs.</div>
          ) : (
            jobs.map((job) => {
              const canOpen = job.status === "done" && job.world_id;
              const canRestart = job.status === "failed";
              return (
                <article key={job.id} className="job-row">
                  <button className="job-main" onClick={() => onSelectJob(job.id)}>
                    <ChevronRight className="job-chevron" size={16} />
                    <span className={`status-dot status-${job.status}`} aria-hidden="true" />
                    <span className="job-text">
                      <span className="job-title">{job.prompt}</span>
                      <span className="job-meta">{job.provider}/{job.model_name} · {formatDate(job.updated_at)}</span>
                    </span>
                    <span className="job-status">{statusLabel(job.status)}</span>
                  </button>

                  {job.error ? <div className="job-error">{job.error}</div> : null}

                  {canOpen || canRestart ? (
                    <div className="job-actions">
                      {canRestart ? (
                        <button className="button secondary" onClick={() => onRestartJob(job.id)}>
                          <RotateCcw size={16} />
                          Restart
                        </button>
                      ) : null}
                      {canOpen ? (
                        <button className="button secondary" onClick={() => onOpenWorld(job.world_id)}>
                          <ExternalLink size={16} />
                          Open
                        </button>
                      ) : null}
                    </div>
                  ) : null}
                </article>
              );
            })
          )}
        </section>
      </div>
    </main>
  );
}

function GenerationJobDetail({ job, loading, error, onBack, onRefresh, onOpenWorld, onRestartJob }) {
  const [collapsedGeneratorRows, setCollapsedGeneratorRows] = useState({});
  const generatorRows = groupGeneratorInstances(job?.steps ?? []);
  const canOpen = job?.status === "done" && job?.world_id;
  const canRestart = job?.status === "failed";
  const toggleGeneratorRow = (rowType) => {
    setCollapsedGeneratorRows((current) => ({ ...current, [rowType]: !current[rowType] }));
  };

  return (
    <main className="content jobs-content">
      <div className="jobs-wrap">
        <div className="content-header job-detail-header">
          <div className="job-detail-title">
            <h1>Generation job</h1>
            <div className="muted">
              {job ? `${statusLabel(job.status)} · ${job.provider}/${job.model_name}` : loading ? "Loading..." : "No job loaded"}
            </div>
            <div className="job-detail-prompt">{job?.prompt ?? ""}</div>
            {job?.updated_at ? <div className="muted">Updated {formatDate(job.updated_at)}</div> : null}
          </div>
          <div className="header-actions">
            <button className="button secondary" onClick={onBack}>
              <ArrowLeft size={16} />
              Back
            </button>
            {canOpen ? (
              <button className="button secondary" onClick={() => onOpenWorld(job.world_id)}>
                <ExternalLink size={16} />
                Open
              </button>
            ) : null}
            {canRestart ? (
              <button className="button secondary" onClick={() => onRestartJob(job.id)}>
                <RotateCcw size={16} />
                Restart
              </button>
            ) : null}
            <button className="button secondary" onClick={onRefresh}>
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>
        </div>

        {error ? <div className="error-banner">{error}</div> : null}
        {job?.error ? <div className="error-banner">{job.error}</div> : null}

        <section className="generator-list-panel">
          {loading && !job ? (
            <div className="empty-panel">Loading generation job.</div>
          ) : generatorRows.length === 0 ? (
            <div className="empty-panel">No generator instances recorded.</div>
          ) : (
            generatorRows.map((row) => {
              const collapsed = Boolean(collapsedGeneratorRows[row.type]);
              return (
                <article key={row.type} className="generator-row">
                  <button
                    className="generator-row-head"
                    type="button"
                    onClick={() => toggleGeneratorRow(row.type)}
                    aria-expanded={!collapsed}
                  >
                    <span className="generator-row-title">
                      <ChevronRight className={`generator-row-chevron ${collapsed ? "" : "expanded"}`} size={16} />
                      <span className="generator-type">{row.label}</span>
                    </span>
                    <span className="generator-count">{row.activeCount} active</span>
                  </button>
                  {!collapsed && row.instances.length > 0 ? (
                    <div className="generator-instances">
                      {row.instances.map((instance) => {
                        const title = generatorCardTitle(instance, row);
                        return (
                          <div key={instance.instanceId} className="generator-card">
                            {title ? <div className="generator-card-title">{title}</div> : null}
                            <div className="generator-card-main">
                              <span className={`status-dot status-${instance.status}`} aria-hidden="true" />
                              <span className="generator-card-status">{statusLabel(instance.status)}</span>
                            </div>
                            <div>Attempts {instance.attempts}</div>
                            <div>{generatorInstanceNote(instance)}</div>
                            {instance.error ? <div className="generator-card-error">{instance.error}</div> : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                </article>
              );
            })
          )}
        </section>
      </div>
    </main>
  );
}

function PlaceMap({ places, selectedId, onSelect }) {
  return (
    <div className="map-box">
      {places.map((place) => (
        <button
          key={place.id}
          className={`map-point danger-${place.danger_level} ${selectedId === place.id ? "active" : ""}`}
          style={{ left: `${place.x}%`, top: `${place.y}%` }}
          onClick={() => onSelect(place)}
          title={`${place.name} (${place.place_type})`}
        >
          <MapPin size={15} />
        </button>
      ))}
    </div>
  );
}

function DataTable({ rows, columns, onRowClick, selectedId }) {
  const [sorting, setSorting] = useState([]);
  const tableColumns = useMemo(
    () => columns.map((column) => ({
      id: column.key,
      accessorKey: column.key,
      header: column.label,
      cell: ({ row, getValue }) => (column.render ? column.render(row.original) : getValue()),
    })),
    [columns],
  );
  const table = useReactTable({
    data: rows,
    columns: tableColumns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  });

  if (!rows.length) {
    return <div className="empty-panel">No records.</div>;
  }

  return (
    <div className="table-wrap">
      <table>
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th key={header.id}>
                  {header.isPlaceholder ? null : (
                    <button
                      className="table-sort-button"
                      type="button"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      {flexRender(header.column.columnDef.header, header.getContext())}
                      <span className="table-sort-indicator">
                        {header.column.getIsSorted() === "asc" ? "Asc" : header.column.getIsSorted() === "desc" ? "Desc" : ""}
                      </span>
                    </button>
                  )}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr
              key={row.original.id ?? row.id}
              className={`${selectedId === row.original.id ? "selected-row" : ""} ${onRowClick ? "clickable-row" : ""}`}
              onClick={() => onRowClick?.(row.original)}
            >
              {row.getVisibleCells().map((cell) => (
                <td key={cell.id}>{flexRender(cell.column.columnDef.cell, cell.getContext())}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function LorePanel({ lore, loading }) {
  return (
    <aside className="lore-panel">
      {loading ? (
        <div className="empty-panel">Loading lore...</div>
      ) : lore ? (
        <ReactMarkdown>{lore}</ReactMarkdown>
      ) : (
        <div className="empty-panel">Select a record to read lore.</div>
      )}
    </aside>
  );
}

function ItemCarriers({ item }) {
  const carriers = item?.carriers ?? [];
  return (
    <section className="item-carriers">
      <div className="item-detail-header">
        <div>
          <div className="field-label">Carried by</div>
          <p>{item ? `${item.name} is currently carried by ${item.carrier_count} NPC${item.carrier_count === 1 ? "" : "s"}.` : "Select an item to inspect who carries it."}</p>
        </div>
      </div>
      {carriers.length === 0 ? (
        <div className="empty-panel">No one is carrying this item right now.</div>
      ) : (
        <DataTable
          rows={carriers}
          columns={[
            { key: "npc_name", label: "NPC" },
            { key: "quantity", label: "Qty" },
            { key: "condition", label: "Condition" },
            { key: "note", label: "Note" },
          ]}
        />
      )}
    </section>
  );
}

function WorldDetail({ world, data, activeTab, setActiveTab, selectedEntity, setSelectedEntity, lore, loreLoading, onDelete }) {
  const tabs = ["overview", "places", "npcs", "factions", "items", "relationships", "lore"];
  const places = data.places ?? [];
  const npcs = data.npcs ?? [];
  const factions = data.factions ?? [];
  const items = data.items ?? [];
  const relationships = data.relationships ?? [];

  const selectedPlace = selectedEntity?.type === "places" ? selectedEntity.row : places[0];
  const selectedItem = selectedEntity?.type === "items" || selectedEntity?.type === "staple-items" ? selectedEntity.row : items[0];
  const placeById = useMemo(() => new Map(places.map((place) => [place.id, place])), [places]);
  const npcsWithLocation = useMemo(
    () => npcs.map((npc) => {
      const place = placeById.get(npc.current_place_id) || placeById.get(npc.home_place_id);
      return { ...npc, location: place?.name || "Unknown location" };
    }),
    [npcs, placeById],
  );

  return (
    <main className="content">
      <div className="content-header">
        <div>
          <h1>{world.title}</h1>
          <div className="muted">{world.region?.name} · {world.provider}/{world.model_name}</div>
        </div>
        <button className="button danger" onClick={onDelete}>
          <Trash2 size={16} />
          Delete
        </button>
      </div>

      <nav className="tabs">
        {tabs.map((tab) => (
          <button
            key={tab}
            className={activeTab === tab ? "active" : ""}
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
        <section className="split">
          <div className="main-panel">
            <div className="summary-grid">
              <div>
                <div className="field-label">Summary</div>
                <p>{world.region?.summary}</p>
              </div>
              <div>
                <div className="field-label">Climate</div>
                <p>{world.region?.climate}</p>
              </div>
              <div>
                <div className="field-label">Danger profile</div>
                <p>{world.region?.danger_profile}</p>
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
        <section className="split">
          <div className="main-panel">
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
        <section className="split">
          <div className="main-panel">
            <DataTable
              rows={npcsWithLocation}
              selectedId={selectedEntity?.row?.id}
              onRowClick={(row) => setSelectedEntity({ type: "npcs", row })}
              columns={[
                { key: "name", label: "Name" },
                { key: "location", label: "Location" },
                { key: "age", label: "Age" },
                { key: "job", label: "Job" },
                { key: "personality", label: "Personality" },
                { key: "status", label: "Status" },
              ]}
            />
          </div>
          <LorePanel lore={lore} loading={loreLoading} />
        </section>
      ) : null}

      {activeTab === "factions" ? (
        <section className="split">
          <div className="main-panel">
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
        <section className="split">
          <div className="main-panel">
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
        <section className="main-panel">
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
        <section className="main-panel lore-full">
          <ReactMarkdown>{lore || "Select a place, NPC, faction, item, or overview region first."}</ReactMarkdown>
        </section>
      ) : null}
    </main>
  );
}

function App() {
  const initialRoute = routeFromPath();
  const [worlds, setWorlds] = useState([]);
  const [jobs, setJobs] = useState([]);
  const [jobsLoading, setJobsLoading] = useState(false);
  const [selectedJobId, setSelectedJobId] = useState(initialRoute.jobId);
  const [selectedJob, setSelectedJob] = useState(null);
  const [jobDetailLoading, setJobDetailLoading] = useState(false);
  const [selectedWorldId, setSelectedWorldId] = useState("");
  const [world, setWorld] = useState(null);
  const [data, setData] = useState({ places: [], npcs: [], factions: [], items: [], inventory: [], relationships: [] });
  const [models, setModels] = useState([]);
  const [activeModelId, setActiveModelId] = useState("");
  const [modelStatus, setModelStatus] = useState("idle");
  const [modelTestResult, setModelTestResult] = useState(null);
  const [mode, setMode] = useState(initialRoute.mode);
  const [prompt, setPrompt] = useState("");
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [activeTab, setActiveTab] = useState("overview");
  const [selectedEntity, setSelectedEntity] = useState({ type: "region", row: { id: "region" } });
  const [lore, setLore] = useState("");
  const [loreLoading, setLoreLoading] = useState(false);

  const activeModel = useMemo(() => models.find((model) => model.id === activeModelId), [models, activeModelId]);

  const navigateMode = (nextMode, path = "/", nextJobId = "") => {
    if (window.location.pathname !== path) {
      window.history.pushState({}, "", path);
    }
    setMode(nextMode);
    setSelectedJobId(nextJobId);
  };

  const loadWorlds = async () => {
    const payload = await request("/worlds");
    setWorlds(payload.worlds ?? []);
    return payload.worlds ?? [];
  };

  const loadGenerationJobs = async () => {
    setJobsLoading(true);
    try {
      const payload = await request("/generation-jobs");
      setJobs(payload.jobs ?? []);
      return payload.jobs ?? [];
    } finally {
      setJobsLoading(false);
    }
  };

  const loadGenerationJob = async (jobId) => {
    if (!jobId) return null;
    setSelectedJob(null);
    setJobDetailLoading(true);
    try {
      const payload = await request(`/generation-jobs/${encodeURIComponent(jobId)}`);
      setSelectedJob(payload.job ?? null);
      return payload.job ?? null;
    } finally {
      setJobDetailLoading(false);
    }
  };

  const loadModels = async () => {
    const [catalog, active] = await Promise.all([request("/models"), request("/models/active")]);
    setModels(catalog.models ?? []);
    setActiveModelId(active.id ?? catalog.models?.[0]?.id ?? "");
  };

  const loadWorld = async (worldId) => {
    const [worldPayload, placesPayload, npcsPayload, factionsPayload, itemsPayload, inventoryPayload, relationshipsPayload] = await Promise.all([
      request(`/worlds/${encodeURIComponent(worldId)}`),
      request(`/worlds/${encodeURIComponent(worldId)}/places`),
      request(`/worlds/${encodeURIComponent(worldId)}/npcs`),
      request(`/worlds/${encodeURIComponent(worldId)}/factions`),
      request(`/worlds/${encodeURIComponent(worldId)}/items`),
      request(`/worlds/${encodeURIComponent(worldId)}/npc-inventory`),
      request(`/worlds/${encodeURIComponent(worldId)}/relationships`),
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
    setSelectedWorldId(worldId);
    navigateMode("detail");
    setActiveTab("overview");
    setSelectedEntity({ type: "region", row: { id: "region" } });
  };

  useEffect(() => {
    loadModels().catch((loadError) => setError(loadError.message));
    loadGenerationJobs().catch((loadError) => setError(loadError.message));
    const startsOnJobsRoute = window.location.pathname === "/jobs" || window.location.pathname.startsWith("/jobs/");
    if (initialRoute.mode === "job-detail" && initialRoute.jobId) {
      loadGenerationJob(initialRoute.jobId).catch((loadError) => setError(loadError.message));
    }
    loadWorlds()
      .then((items) => {
        if (items.length > 0 && !startsOnJobsRoute) {
          loadWorld(items[0].id).catch((loadError) => setError(loadError.message));
        }
      })
      .catch((loadError) => setError(loadError.message));
  }, []);

  useEffect(() => {
    const handlePopState = () => {
      const route = routeFromPath();
      setMode(route.mode);
      setSelectedJobId(route.jobId);
      if (window.location.pathname === "/jobs") {
        loadGenerationJobs().catch((loadError) => setError(loadError.message));
      } else if (route.mode === "job-detail" && route.jobId) {
        loadGenerationJob(route.jobId).catch((loadError) => setError(loadError.message));
      }
    };
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    if (mode !== "jobs") {
      return undefined;
    }
    let cancelled = false;
    const pollJobs = async () => {
      try {
        const payload = await request("/generation-jobs");
        if (!cancelled) {
          setJobs(payload.jobs ?? []);
          loadWorlds().catch(() => {});
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError.message);
      }
    };
    pollJobs();
    const intervalId = window.setInterval(pollJobs, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [mode]);

  useEffect(() => {
    if (mode !== "job-detail" || !selectedJobId) {
      return undefined;
    }
    let cancelled = false;
    const pollJob = async () => {
      try {
        const payload = await request(`/generation-jobs/${encodeURIComponent(selectedJobId)}`);
        if (!cancelled) {
          setSelectedJob(payload.job ?? null);
          loadWorlds().catch(() => {});
        }
      } catch (loadError) {
        if (!cancelled) setError(loadError.message);
      }
    };
    pollJob();
    const intervalId = window.setInterval(pollJob, 4000);
    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [mode, selectedJobId]);

  useEffect(() => {
    if (!selectedWorldId || !selectedEntity?.type) {
      setLore("");
      return;
    }
    const entityType = selectedEntity.type;
    const entityId = selectedEntity.row?.id ?? "region";
    setLoreLoading(true);
    request(`/worlds/${encodeURIComponent(selectedWorldId)}/lore/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`)
      .then((payload) => setLore(payload.content ?? ""))
      .catch(() => setLore(""))
      .finally(() => setLoreLoading(false));
  }, [selectedWorldId, selectedEntity]);

  const createWorld = async () => {
    setCreating(true);
    setError("");
    try {
      await request("/worlds", {
        method: "POST",
        body: JSON.stringify({ prompt, model_id: activeModelId }),
      });
      setPrompt("");
      navigateMode("jobs", "/jobs");
      await loadGenerationJobs();
    } catch (createError) {
      setError(createError.message);
    } finally {
      setCreating(false);
    }
  };

  const selectModel = async (modelId) => {
    setActiveModelId(modelId);
    setModelStatus("idle");
    setModelTestResult(null);
    try {
      await request("/models/active", {
        method: "PUT",
        body: JSON.stringify({ model_id: modelId }),
      });
    } catch (selectError) {
      setError(selectError.message);
    }
  };

  const testModel = async () => {
    if (!activeModel) return;
    setModelStatus("testing");
    setModelTestResult(null);
    try {
      const payload = await request("/models/test", {
        method: "POST",
        body: JSON.stringify({ models: [activeModel] }),
      });
      const result = payload.results?.[0];
      if (!result) {
        setModelStatus("failed");
        setModelTestResult({ error: "Model test returned no result." });
        return;
      }
      setModelStatus(result.ok ? "ok" : "failed");
      setModelTestResult({
        latency_ms: result.latency_ms,
        response_preview: result.response_preview,
        error: result.error || (result.ok ? "" : "Model test failed."),
      });
    } catch (testError) {
      setModelStatus("failed");
      setModelTestResult({ error: testError.message });
    }
  };

  const deleteSelectedWorld = async () => {
    if (!selectedWorldId) return;
    const confirmed = window.confirm(`Delete "${world?.title ?? selectedWorldId}"?`);
    if (!confirmed) return;
    await request(`/worlds/${encodeURIComponent(selectedWorldId)}`, { method: "DELETE" });
    const next = await loadWorlds();
    if (next.length > 0) {
      await loadWorld(next[0].id);
    } else {
      setSelectedWorldId("");
      setWorld(null);
      navigateMode("create");
    }
  };

  const clearFinishedJobs = async () => {
    const confirmed = window.confirm("Clear finished and failed generation jobs?");
    if (!confirmed) return;
    const payload = await request("/generation-jobs/finished", { method: "DELETE" });
    setJobs(payload.jobs ?? []);
  };

  const clearActiveJobs = async () => {
    const confirmed = window.confirm("Clear pending and running generation jobs? Running generation will be stopped.");
    if (!confirmed) return;
    const payload = await request("/generation-jobs/active", { method: "DELETE" });
    setJobs(payload.jobs ?? []);
    await loadWorlds();
  };

  const restartGenerationJob = async (jobId) => {
    if (!jobId) return;
    if (!activeModelId) {
      throw new Error("Select a model before restarting this job.");
    }
    setError("");
    const params = new URLSearchParams({ model_id: activeModelId });
    const payload = await request(`/generation-jobs/${encodeURIComponent(jobId)}/restart?${params.toString()}`, {
      method: "POST",
      body: JSON.stringify({ model_id: activeModelId }),
    });
    setSelectedJob(payload.job ?? null);
    await loadGenerationJobs();
  };

  return (
    <div className="app-shell">
      <Sidebar
        worlds={worlds}
        selectedWorldId={selectedWorldId}
        onSelectWorld={(id) => loadWorld(id).catch((loadError) => setError(loadError.message))}
        onNewWorld={() => {
          navigateMode("create");
          setError("");
        }}
        onShowJobs={() => {
          navigateMode("jobs", "/jobs");
          setError("");
          loadGenerationJobs().catch((loadError) => setError(loadError.message));
        }}
        onRefresh={() => loadWorlds().catch((loadError) => setError(loadError.message))}
        models={models}
        activeModelId={activeModelId}
        onSelectModel={selectModel}
        onTestModel={testModel}
        modelStatus={modelStatus}
        modelTestResult={modelTestResult}
      />

      {mode === "jobs" ? (
        <GenerationJobs
          jobs={jobs}
          loading={jobsLoading}
          error={error}
          onRefresh={() => loadGenerationJobs().catch((loadError) => setError(loadError.message))}
          onSelectJob={(jobId) => {
            navigateMode("job-detail", `/jobs/${encodeURIComponent(jobId)}`, jobId);
            setError("");
            loadGenerationJob(jobId).catch((loadError) => setError(loadError.message));
          }}
          onOpenWorld={(worldId) => loadWorld(worldId).catch((loadError) => setError(loadError.message))}
          onRestartJob={(jobId) => restartGenerationJob(jobId).catch((restartError) => setError(restartError.message))}
          onClearFinished={() => clearFinishedJobs().catch((clearError) => setError(clearError.message))}
          onClearActive={() => clearActiveJobs().catch((clearError) => setError(clearError.message))}
        />
      ) : mode === "job-detail" ? (
        <GenerationJobDetail
          job={selectedJob}
          loading={jobDetailLoading}
          error={error}
          onBack={() => {
            navigateMode("jobs", "/jobs");
            setError("");
            loadGenerationJobs().catch((loadError) => setError(loadError.message));
          }}
          onRefresh={() => loadGenerationJob(selectedJobId).catch((loadError) => setError(loadError.message))}
          onOpenWorld={(worldId) => loadWorld(worldId).catch((loadError) => setError(loadError.message))}
          onRestartJob={(jobId) => restartGenerationJob(jobId).catch((restartError) => setError(restartError.message))}
        />
      ) : mode === "detail" && world ? (
        <WorldDetail
          world={world}
          data={data}
          activeTab={activeTab}
          setActiveTab={setActiveTab}
          selectedEntity={selectedEntity}
          setSelectedEntity={setSelectedEntity}
          lore={lore}
          loreLoading={loreLoading}
          onDelete={() => deleteSelectedWorld().catch((deleteError) => setError(deleteError.message))}
        />
      ) : (
        <CreateWorld prompt={prompt} setPrompt={setPrompt} onSubmit={createWorld} creating={creating} error={error} />
      )}
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
