import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, api, tryGet } from "@/lib/api";
import type { Business, ConversationDetail } from "@/lib/types";
import { Badge, Card, formatDateTime } from "@/components/ui";

export const dynamic = "force-dynamic";

export default async function ConversationPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  let conversation: ConversationDetail;
  try {
    conversation = await api.get<ConversationDetail>(`/api/conversations/${id}`);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }
  const business = await tryGet<Business>("/api/business");

  return (
    <div className="space-y-6">
      <Link href="/dashboard" className="text-sm text-indigo-400 hover:underline">
        ← Back to conversations
      </Link>

      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">
            {conversation.customer_name ?? "Unknown caller"}
          </h1>
          <p className="mt-1 text-sm text-slate-400">
            {conversation.channel} · started{" "}
            {formatDateTime(conversation.started_at, business?.timezone)}
            {conversation.customer_email ? ` · ${conversation.customer_email}` : ""}
          </p>
        </div>
        <Badge value={conversation.outcome} />
      </div>

      <Card title="Transcript">
        <ol className="space-y-4">
          {conversation.messages.map((message) => (
            <li
              key={message.id}
              className={message.role === "customer" ? "flex justify-start" : "flex justify-end"}
            >
              <div
                className={`max-w-[75%] rounded-2xl px-4 py-2.5 text-sm ${
                  message.role === "customer"
                    ? "bg-slate-800 text-slate-100"
                    : "bg-indigo-500/15 text-indigo-100 ring-1 ring-inset ring-indigo-500/30"
                }`}
              >
                <p className="whitespace-pre-wrap">{message.content}</p>
                <p className="mt-1.5 text-[11px] text-slate-500">
                  {message.role}
                  {/* The routed intent is the interesting bit: it shows which agent replied. */}
                  {message.intent ? ` · ${message.intent}` : ""} ·{" "}
                  {formatDateTime(message.created_at, business?.timezone)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
