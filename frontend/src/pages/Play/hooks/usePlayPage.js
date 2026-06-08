import { useCallback, useEffect, useState } from "react";
import { request } from "../../../api/client.js";

export function usePlayPage({ worldId, setError }) {
  const [playState, setPlayState] = useState(null);
  const [loading, setLoading] = useState(false);
  const [inputLoading, setInputLoading] = useState(false);

  const loadPlayState = useCallback(async () => {
    if (!worldId) return null;
    setLoading(true);
    try {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/play`);
      setPlayState(payload);
      return payload;
    } finally {
      setLoading(false);
    }
  }, [worldId]);

  useEffect(() => {
    if (!worldId) {
      setPlayState(null);
      return;
    }
    loadPlayState().catch((loadError) => setError(loadError.message));
  }, [worldId, loadPlayState, setError]);

  const submitPlayInput = async (input) => {
    if (!worldId) return;
    setInputLoading(true);
    setError("");
    try {
      const payload = await request(`/worlds/${encodeURIComponent(worldId)}/play/input`, {
        method: "POST",
        body: JSON.stringify({ input }),
      });
      setPlayState(payload);
    } catch (inputError) {
      setError(inputError.message);
      await loadPlayState().catch(() => {});
      throw inputError;
    } finally {
      setInputLoading(false);
    }
  };

  return {
    playState,
    loading,
    inputLoading,
    submitPlayInput,
  };
}
