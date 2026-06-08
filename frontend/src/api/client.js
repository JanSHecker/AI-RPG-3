export const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function request(path, options = {}) {
  const { signal, headers, ...rest } = options;
  const response = await fetch(`${API_URL}${path}`, {
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
    ...(signal ? { signal } : {}),
    ...rest,
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
