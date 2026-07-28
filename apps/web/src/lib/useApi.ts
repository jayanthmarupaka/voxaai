"use client";

/** Browser-side API calls. The Clerk token is attached per request. */

import { useAuth } from "@clerk/nextjs";
import { useCallback } from "react";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000";

export function useApi() {
  const { getToken } = useAuth();

  return useCallback(
    async <T,>(path: string, init: RequestInit = {}): Promise<T> => {
      const token = await getToken();
      const isFormData = init.body instanceof FormData;

      const response = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: {
          ...(init.body && !isFormData ? { "Content-Type": "application/json" } : {}),
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
          ...init.headers,
        },
      });

      if (!response.ok) {
        let detail = response.statusText;
        try {
          detail = (await response.json())?.detail ?? detail;
        } catch {
          // Keep the status text.
        }
        throw new Error(detail);
      }
      if (response.status === 204) return undefined as T;
      return (await response.json()) as T;
    },
    [getToken],
  );
}
