"use client";

import { useEffect, useState, useTransition } from "react";
import { useApi } from "@/lib/useApi";
import type { FollowUp, FollowUpStatus } from "@/lib/types";
import { Badge, Card, EmptyState, formatDateTime } from "@/components/ui";

export function FollowUpList() {
  const call = useApi();
  const [items, setItems] = useState<FollowUp[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [, startTransition] = useTransition();

  useEffect(() => {
    call<FollowUp[]>("/api/follow-ups")
      .then(setItems)
      .catch((cause: Error) => setError(cause.message));
  }, [call]);

  function setStatus(id: string, status: FollowUpStatus) {
    // Optimistic: the list is small and a failure re-reads from the server.
    setItems((current) =>
      current?.map((item) => (item.id === id ? { ...item, status } : item)) ?? null,
    );
    startTransition(async () => {
      try {
        const updated = await call<FollowUp>(`/api/follow-ups/${id}`, {
          method: "PATCH",
          body: JSON.stringify({ status }),
        });
        setItems((current) =>
          current?.map((item) => (item.id === id ? updated : item)) ?? null,
        );
      } catch (cause) {
        setError((cause as Error).message);
        setItems(await call<FollowUp[]>("/api/follow-ups"));
      }
    });
  }

  if (error) return <EmptyState>{error}</EmptyState>;
  if (!items) return <EmptyState>Loading…</EmptyState>;
  if (items.length === 0) {
    return <EmptyState>Nothing needs a human right now.</EmptyState>;
  }

  return (
    <Card>
      <ul className="divide-y divide-slate-800">
        {items.map((item) => (
          <li key={item.id} className="flex flex-wrap items-start justify-between gap-4 py-4">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-slate-100">{item.question}</p>
                <Badge value={item.status} />
              </div>
              <p className="mt-1.5 text-xs text-slate-500">
                {item.customer_name ?? "Unknown caller"}
                {item.customer_email ? ` · ${item.customer_email}` : ""}
                {item.customer_phone ? ` · ${item.customer_phone}` : ""} ·{" "}
                {formatDateTime(item.created_at)}
              </p>
            </div>
            {item.status === "open" ? (
              <button
                onClick={() => setStatus(item.id, "resolved")}
                className="rounded-lg bg-emerald-500/15 px-3 py-1.5 text-xs font-medium text-emerald-300 ring-1 ring-inset ring-emerald-500/30 hover:bg-emerald-500/25"
              >
                Mark resolved
              </button>
            ) : (
              <button
                onClick={() => setStatus(item.id, "open")}
                className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-inset ring-slate-700 hover:text-slate-200"
              >
                Reopen
              </button>
            )}
          </li>
        ))}
      </ul>
    </Card>
  );
}
