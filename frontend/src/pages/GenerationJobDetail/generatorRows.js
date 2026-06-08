import { formatDate } from "../../shared/lib/format.js";

export function generatorInstanceNote(step) {
  if (step.latency_ms) return `${step.latency_ms} ms`;
  if (step.started_at) return `Started ${formatDate(step.started_at)}`;
  if (step.finished_at) return `Finished ${formatDate(step.finished_at)}`;
  return "Waiting";
}

export function generatorGroupType(step, index) {
  const type = step.step_name || `step-${index}`;
  if (type.startsWith("places_")) return "villages_places";
  if (type.startsWith("npcs_")) return "npcs";
  return type;
}

export function generatorGroupLabel(type, step) {
  if (type === "villages_places") return "Villages & Places";
  if (type === "npcs") return "NPCs";
  return step.label || type;
}

export function generatorCardTitle(instance, row) {
  if (instance.step_name === row.type && row.instances.length > 1) return "Overall";
  if (instance.step_name?.startsWith("places_")) return instance.label || "Places batch";
  if (instance.step_name?.startsWith("npcs_")) return instance.label || "NPC batch";
  return "";
}

export function hasVisibleGeneratorProgress(step) {
  if (!step) return false;
  if (step.status && step.status !== "pending") return true;
  if (Number(step.attempts || 0) > 0) return true;
  return Boolean(step.error || step.raw_response || step.parsed_payload || step.started_at || step.finished_at);
}

export function isRetryableBatchStep(stepName = "") {
  return stepName.startsWith("places_") || stepName.startsWith("npcs_") || stepName.startsWith("relationships_");
}

export function groupGeneratorInstances(steps = []) {
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
