import Link from "next/link";
import { tryGet } from "@/lib/api";
import type { Booking, Business, Conversation, FollowUp } from "@/lib/types";
import { Badge, Card, EmptyState, formatDateTime, formatRelative } from "@/components/ui";

export const dynamic = "force-dynamic";

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-5 py-4">
      <p className="text-xs uppercase tracking-wide text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-100">{value}</p>
    </div>
  );
}

export default async function DashboardPage() {
  const [business, conversations, bookings, followUps] = await Promise.all([
    tryGet<Business>("/api/business"),
    tryGet<Conversation[]>("/api/conversations?limit=25"),
    tryGet<Booking[]>("/api/bookings?limit=5"),
    tryGet<FollowUp[]>("/api/follow-ups?status=open"),
  ]);

  if (!business) {
    return (
      <EmptyState>
        Could not reach the Voxa API. Check that it is running and that{" "}
        <code className="text-slate-300">NEXT_PUBLIC_API_URL</code> points at it.
      </EmptyState>
    );
  }

  const list = conversations ?? [];
  const booked = list.filter((item) => item.outcome === "booked").length;

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{business.name}</h1>
        <p className="mt-1 text-sm text-slate-400">
          Share{" "}
          <Link
            href={`/demo/${business.id}`}
            className="text-indigo-400 underline underline-offset-4"
          >
            your receptionist link
          </Link>{" "}
          to take a call. Times are shown in {business.timezone}.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-4">
        <Stat label="Conversations" value={list.length} />
        <Stat label="Booked" value={booked} />
        <Stat label="Appointments" value={bookings?.length ?? 0} />
        <Stat label="Needs a human" value={followUps?.length ?? 0} />
      </div>

      <Card title="Recent conversations">
        {list.length === 0 ? (
          <EmptyState>
            No calls yet. Open the receptionist link and say &ldquo;can I book a cleaning on
            Tuesday?&rdquo;
          </EmptyState>
        ) : (
          <ul className="divide-y divide-slate-800">
            {list.map((conversation) => (
              <li key={conversation.id}>
                <Link
                  href={`/dashboard/conversations/${conversation.id}`}
                  className="flex items-center justify-between gap-4 py-3 hover:opacity-80"
                >
                  <div className="min-w-0">
                    <p className="truncate text-sm text-slate-200">
                      {conversation.customer_name ?? "Unknown caller"}
                      <span className="ml-2 text-xs text-slate-500">{conversation.channel}</span>
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      {formatRelative(conversation.started_at)}
                    </p>
                  </div>
                  <Badge value={conversation.outcome} />
                </Link>
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title="Latest appointments"
        action={
          <Link href="/dashboard/bookings" className="text-xs text-indigo-400 hover:underline">
            View all
          </Link>
        }
      >
        {!bookings || bookings.length === 0 ? (
          <EmptyState>Nothing booked yet.</EmptyState>
        ) : (
          <ul className="divide-y divide-slate-800">
            {bookings.map((booking) => (
              <li key={booking.id} className="flex items-center justify-between gap-4 py-3">
                <div>
                  <p className="text-sm text-slate-200">{booking.customer_name}</p>
                  <p className="text-xs text-slate-500">
                    {booking.service ?? "Appointment"} ·{" "}
                    {formatDateTime(booking.starts_at, business.timezone)}
                  </p>
                </div>
                <Badge value={booking.status} />
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
