"use client";

import { useEffect, useState } from "react";
import { useApi } from "@/lib/useApi";
import type { Business, BusinessHours, GoogleStatus, ServiceItem } from "@/lib/types";
import { Card, EmptyState } from "@/components/ui";

const DAYS: { key: string; label: string }[] = [
  { key: "mon", label: "Monday" },
  { key: "tue", label: "Tuesday" },
  { key: "wed", label: "Wednesday" },
  { key: "thu", label: "Thursday" },
  { key: "fri", label: "Friday" },
  { key: "sat", label: "Saturday" },
  { key: "sun", label: "Sunday" },
];

const TIME_PATTERN = /^\d{2}:\d{2}$/;

export function SettingsForm({ googleResult }: { googleResult?: string }) {
  const call = useApi();
  const [business, setBusiness] = useState<Business | null>(null);
  const [google, setGoogle] = useState<GoogleStatus | null>(null);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([call<Business>("/api/business"), call<GoogleStatus>("/api/integrations/google/status")])
      .then(([loadedBusiness, loadedGoogle]) => {
        setBusiness(loadedBusiness);
        setGoogle(loadedGoogle);
      })
      .catch((cause: Error) => setError(cause.message));
  }, [call]);

  function setHours(day: string, index: 0, field: "open" | "close", value: string) {
    setBusiness((current) => {
      if (!current) return current;
      const hours: BusinessHours = { ...current.business_hours };
      const windows = [...(hours[day] ?? [])];
      windows[index] = { ...(windows[index] ?? { open: "09:00", close: "17:00" }), [field]: value };
      hours[day] = windows;
      return { ...current, business_hours: hours };
    });
  }

  function toggleDay(day: string, openDay: boolean) {
    setBusiness((current) => {
      if (!current) return current;
      const hours: BusinessHours = { ...current.business_hours };
      hours[day] = openDay ? [{ open: "09:00", close: "17:00" }] : [];
      return { ...current, business_hours: hours };
    });
  }

  function setService(index: number, patch: Partial<ServiceItem>) {
    setBusiness((current) => {
      if (!current) return current;
      const services = current.services.map((service, position) =>
        position === index ? { ...service, ...patch } : service,
      );
      return { ...current, services };
    });
  }

  async function save() {
    if (!business) return;
    // The API rejects malformed times, but catching it here gives a better message.
    const bad = Object.values(business.business_hours)
      .flat()
      .find((window) => !TIME_PATTERN.test(window.open) || !TIME_PATTERN.test(window.close));
    if (bad) {
      setError("Opening hours must look like 09:00.");
      return;
    }

    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const updated = await call<Business>("/api/business", {
        method: "PATCH",
        body: JSON.stringify({
          name: business.name,
          timezone: business.timezone,
          greeting: business.greeting,
          business_hours: business.business_hours,
          services: business.services,
        }),
      });
      setBusiness(updated);
      setMessage("Saved.");
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setSaving(false);
    }
  }

  async function connectGoogle() {
    try {
      const { authorization_url } = await call<{ authorization_url: string }>(
        "/api/integrations/google/authorize",
      );
      window.location.href = authorization_url;
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  async function disconnectGoogle() {
    try {
      await call<void>("/api/integrations/google/disconnect", { method: "DELETE" });
      setGoogle(await call<GoogleStatus>("/api/integrations/google/status"));
    } catch (cause) {
      setError((cause as Error).message);
    }
  }

  if (error && !business) return <EmptyState>{error}</EmptyState>;
  if (!business) return <EmptyState>Loading…</EmptyState>;

  return (
    <div className="space-y-6">
      {googleResult === "connected" && (
        <p className="rounded-lg bg-emerald-500/10 px-4 py-3 text-sm text-emerald-300">
          Google Calendar connected.
        </p>
      )}
      {googleResult && googleResult !== "connected" && (
        <p className="rounded-lg bg-rose-500/10 px-4 py-3 text-sm text-rose-300">
          Google Calendar connection failed: {googleResult.replace(/_/g, " ")}.
        </p>
      )}

      <Card title="Receptionist">
        <div className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm">
            <span className="text-slate-400">Business name</span>
            <input
              value={business.name}
              onChange={(event) => setBusiness({ ...business, name: event.target.value })}
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-indigo-500"
            />
          </label>
          <label className="block text-sm">
            <span className="text-slate-400">Timezone (IANA)</span>
            <input
              value={business.timezone}
              onChange={(event) => setBusiness({ ...business, timezone: event.target.value })}
              placeholder="Europe/London"
              className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-indigo-500"
            />
          </label>
        </div>
        <label className="mt-4 block text-sm">
          <span className="text-slate-400">Opening line</span>
          <textarea
            value={business.greeting}
            rows={2}
            onChange={(event) => setBusiness({ ...business, greeting: event.target.value })}
            className="mt-1 w-full rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-indigo-500"
          />
        </label>
      </Card>

      <Card title="Opening hours">
        <ul className="space-y-2">
          {DAYS.map(({ key, label }) => {
            const windows = business.business_hours[key] ?? [];
            const isOpen = windows.length > 0;
            return (
              <li key={key} className="flex flex-wrap items-center gap-3 text-sm">
                <label className="flex w-32 items-center gap-2">
                  <input
                    type="checkbox"
                    checked={isOpen}
                    onChange={(event) => toggleDay(key, event.target.checked)}
                    className="accent-indigo-500"
                  />
                  <span className="text-slate-300">{label}</span>
                </label>
                {isOpen ? (
                  <>
                    <input
                      type="time"
                      value={windows[0].open}
                      onChange={(event) => setHours(key, 0, "open", event.target.value)}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                    />
                    <span className="text-slate-600">to</span>
                    <input
                      type="time"
                      value={windows[0].close}
                      onChange={(event) => setHours(key, 0, "close", event.target.value)}
                      className="rounded-lg border border-slate-700 bg-slate-900 px-2 py-1 text-slate-100"
                    />
                  </>
                ) : (
                  <span className="text-slate-600">closed</span>
                )}
              </li>
            );
          })}
        </ul>
      </Card>

      <Card
        title="Services"
        action={
          <button
            onClick={() =>
              setBusiness({
                ...business,
                services: [...business.services, { name: "", duration_minutes: 30 }],
              })
            }
            className="text-xs text-indigo-400 hover:underline"
          >
            Add service
          </button>
        }
      >
        <p className="mb-3 text-sm text-slate-400">
          Duration decides how long a slot is held on the calendar.
        </p>
        {business.services.length === 0 ? (
          <EmptyState>No services yet — bookings default to 30 minutes.</EmptyState>
        ) : (
          <ul className="space-y-2">
            {business.services.map((service, index) => (
              <li key={index} className="flex items-center gap-3 text-sm">
                <input
                  value={service.name}
                  placeholder="Cleaning"
                  onChange={(event) => setService(index, { name: event.target.value })}
                  className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-indigo-500"
                />
                <input
                  type="number"
                  min={5}
                  max={480}
                  step={5}
                  value={service.duration_minutes}
                  onChange={(event) =>
                    setService(index, { duration_minutes: Number(event.target.value) })
                  }
                  className="w-24 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-slate-100 outline-none focus:border-indigo-500"
                />
                <span className="text-slate-500">min</span>
                <button
                  onClick={() =>
                    setBusiness({
                      ...business,
                      services: business.services.filter((_, position) => position !== index),
                    })
                  }
                  className="text-xs text-slate-500 hover:text-rose-400"
                >
                  Remove
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card title="Google Calendar">
        {!google?.oauth_configured ? (
          <p className="text-sm text-slate-400">
            Google OAuth is not configured on the server. Until it is, Voxa checks availability
            against its own bookings table instead — booking still works, it just won&apos;t see
            events created elsewhere.
          </p>
        ) : google.connected ? (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-300">
              Connected as {google.google_account_email ?? "unknown account"}
              <span className="ml-2 text-xs text-slate-500">
                calendar: {google.calendar_id ?? "primary"}
              </span>
            </p>
            <button
              onClick={() => void disconnectGoogle()}
              className="rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-inset ring-slate-700 hover:text-rose-300"
            >
              Disconnect
            </button>
          </div>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-slate-400">
              Connect a calendar so Voxa sees real busy time before it books.
            </p>
            <button
              onClick={() => void connectGoogle()}
              className="rounded-lg bg-indigo-500 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-400"
            >
              Connect Google Calendar
            </button>
          </div>
        )}
      </Card>

      <div className="flex items-center gap-4">
        <button
          onClick={() => void save()}
          disabled={saving}
          className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save changes"}
        </button>
        {message && <span className="text-sm text-emerald-300">{message}</span>}
        {error && <span className="text-sm text-rose-400">{error}</span>}
      </div>
    </div>
  );
}
