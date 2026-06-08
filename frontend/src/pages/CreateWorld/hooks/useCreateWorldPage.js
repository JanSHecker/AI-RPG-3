import { useState } from "react";
import { request } from "../../../api/client.js";
import { PATH_JOBS, ROUTE_JOBS } from "../../../app/routing.js";

export function useCreateWorldPage({ activeModelId, navigateMode, setError, onAfterCreate }) {
  const [prompt, setPrompt] = useState("");
  const [creating, setCreating] = useState(false);

  const createWorld = async () => {
    setCreating(true);
    setError("");
    try {
      await request("/worlds", {
        method: "POST",
        body: JSON.stringify({ prompt, model_id: activeModelId }),
      });
      setPrompt("");
      navigateMode(ROUTE_JOBS, PATH_JOBS);
      if (onAfterCreate) await onAfterCreate();
    } catch (createError) {
      setError(createError.message);
    } finally {
      setCreating(false);
    }
  };

  return {
    prompt,
    setPrompt,
    creating,
    createWorld,
  };
}
