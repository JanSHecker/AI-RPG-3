import { useCallback, useState } from "react";
import { request } from "../../api/client.js";

export function useWorlds({ setError }) {
  const [worlds, setWorlds] = useState([]);

  const loadWorlds = useCallback(async () => {
    try {
      const payload = await request("/worlds");
      const items = payload.worlds ?? [];
      setWorlds(items);
      return items;
    } catch (loadError) {
      if (setError) setError(loadError.message);
      throw loadError;
    }
  }, [setError]);

  return { worlds, loadWorlds };
}
