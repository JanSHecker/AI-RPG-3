import React from "react";
import { renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

export function renderHookWithClient(hookFn, options = {}) {
  const client = createTestQueryClient();
  const wrapper = ({ children }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
  return { client, ...renderHook(hookFn, { wrapper, ...options }) };
}

export function fetchUrl(fetchSpy, callIndex = 0) {
  const call = fetchSpy.mock.calls[callIndex];
  if (!call) return null;
  const url = call[0];
  return typeof url === "string" ? url : url.toString();
}

export function fetchOptions(fetchSpy, callIndex = 0) {
  const call = fetchSpy.mock.calls[callIndex];
  if (!call) return null;
  return call[1] ?? {};
}

export function mockJson(body, { status = 200, headers } = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...(headers ?? {}) },
  });
}
