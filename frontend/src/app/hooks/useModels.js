import { useCallback, useMemo, useState } from "react";
import { request } from "../../api/client.js";

export function useModels({ setError }) {
  const [models, setModels] = useState([]);
  const [activeModelId, setActiveModelId] = useState("");
  const [modelStatus, setModelStatus] = useState("idle");
  const [modelTestResult, setModelTestResult] = useState(null);

  const activeModel = useMemo(() => models.find((model) => model.id === activeModelId), [models, activeModelId]);

  const loadModels = useCallback(async () => {
    const [catalog, active] = await Promise.all([request("/models"), request("/models/active")]);
    setModels(catalog.models ?? []);
    setActiveModelId(active.id ?? catalog.models?.[0]?.id ?? "");
  }, []);

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

  return {
    models,
    activeModelId,
    modelStatus,
    modelTestResult,
    loadModels,
    selectModel,
    testModel,
  };
}
