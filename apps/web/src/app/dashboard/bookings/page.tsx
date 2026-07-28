import { tryGet } from "@/lib/api";
import type { Booking, Business } from "@/lib/types";
import { Badge, Card, EmptyState, formatDateTime } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function BookingsPage() {
  const [bookings, business] = await Promise.all([
    tryGet<Booking[]>("/api/bookings?limit=100"),
    tryGet<Business>("/api/business"),
  ]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Bookings</h1>
        <p className="mt-1 text-sm text-slate-400">
          Everything Voxa put on the calendar, shown in {business?.timezone ?? "UTC"}.
        </p>
      </div>

      <Card>
        {!bookings || bookings.length === 0 ? (
          <EmptyState>No bookings yet.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="text-xs uppercase tracking-wide text-slate-500">
                <tr className="border-b border-slate-800">
                  <th className="py-2 pr-4 font-medium">When</th>
                  <th className="py-2 pr-4 font-medium">Customer</th>
                  <th className="py-2 pr-4 font-medium">Service</th>
                  <th className="py-2 pr-4 font-medium">Calendar</th>
                  <th className="py-2 font-medium">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {bookings.map((booking) => (
                  <tr key={booking.id}>
                    <td className="py-3 pr-4 text-slate-200">
                      {formatDateTime(booking.starts_at, business?.timezone)}
                    </td>
                    <td className="py-3 pr-4">
                      <p className="text-slate-200">{booking.customer_name}</p>
                      {booking.customer_email && (
                        <p className="text-xs text-slate-500">{booking.customer_email}</p>
                      )}
                    </td>
                    <td className="py-3 pr-4 text-slate-400">{booking.service ?? "—"}</td>
                    <td className="py-3 pr-4 text-slate-400">
                      {booking.google_event_id ? "Google" : "Voxa only"}
                    </td>
                    <td className="py-3">
                      <Badge value={booking.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
