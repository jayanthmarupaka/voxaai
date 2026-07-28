import type { ReactNode } from "react";

const OUTCOME_STYLES: Record<string, string> = {
  booked: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  answered: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  escalated: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  abandoned: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  in_progress: "bg-indigo-500/15 text-indigo-300 ring-indigo-500/30",
  confirmed: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  cancelled: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  rescheduled: "bg-sky-500/15 text-sky-300 ring-sky-500/30",
  completed: "bg-slate-500/15 text-slate-300 ring-slate-500/30",
  ready: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
  failed: "bg-rose-500/15 text-rose-300 ring-rose-500/30",
  processing: "bg-indigo-500/15 text-indigo-300 ring-indigo-500/30",
  pending: "bg-slate-500/15 text-slate-400 ring-slate-500/30",
  open: "bg-amber-500/15 text-amber-300 ring-amber-500/30",
  resolved: "bg-emerald-500/15 text-emerald-300 ring-emerald-500/30",
};

export function Badge({ value }: { value: string }) {
  const style = OUTCOME_STYLES[value] ?? "bg-slate-500/15 text-slate-300 ring-slate-500/30";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium ring-1 ring-inset ${style}`}
    >
      {value.replace(/_/g, " ")}
    </span>
  );
}

export function Card({
  title,
  action,
  children,
}: {
  title?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-xl border border-slate-800 bg-slate-900/60 p-5">
      {(title || action) && (
        <header className="mb-4 flex items-center justify-between gap-4">
          {title && <h2 className="text-sm font-semibold text-slate-200">{title}</h2>}
          {action}
        </header>
      )}
      {children}
    </section>
  );
}

export function EmptyState({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-lg border border-dashed border-slate-800 px-4 py-8 text-center text-sm text-slate-500">
      {children}
    </p>
  );
}

export function formatDateTime(value: string, timeZone?: string) {
  return new Date(value).toLocaleString(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone,
  });
}

export function formatRelative(value: string) {
  const diffMs = Date.now() - new Date(value).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}
