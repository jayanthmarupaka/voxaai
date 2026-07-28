"use client";

import { useEffect, useRef, useState } from "react";
import { API_BASE_URL } from "@/lib/useApi";
import { useVoiceSession } from "@/lib/useVoiceSession";
import type { ChatResponse, PublicBusiness } from "@/lib/types";

type Turn = { role: "customer" | "assistant"; text: string; intent?: string };

const STATE_LABEL: Record<string, string> = {
  idle: "Voice off",
  connecting: "Connecting…",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
};

export function Receptionist({ business }: { business: PublicBusiness }) {
  const [turns, setTurns] = useState<Turn[]>([
    { role: "assistant", text: business.greeting },
  ]);
  const [draft, setDraft] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);

  const voice = useVoiceSession({
    businessId: business.id,
    onTranscript: (text) => setTurns((current) => [...current, { role: "customer", text }]),
    onReply: (text, intent) =>
      setTurns((current) => [...current, { role: "assistant", text, intent }]),
    onError: setError,
  });

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns]);

  async function sendTyped(event: React.FormEvent) {
    event.preventDefault();
    const message = draft.trim();
    if (!message || sending) return;
    setDraft("");
    setError(null);
    setTurns((current) => [...current, { role: "customer", text: message }]);

    // While the socket is open the same graph runs over it, keeping one
    // conversation record instead of splitting voice and typed turns.
    if (voice.state !== "idle" && voice.sendText(message)) return;

    setSending(true);
    try {
      const response = await fetch(`${API_BASE_URL}/api/public/businesses/${business.id}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message, conversation_id: conversationId }),
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? "The receptionist is unavailable.");
      }
      const result = (await response.json()) as ChatResponse;
      setConversationId(result.conversation_id);
      setTurns((current) => [
        ...current,
        { role: "assistant", text: result.reply, intent: result.intent },
      ]);
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setSending(false);
    }
  }

  const active = voice.state !== "idle";

  return (
    <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col gap-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">{business.name}</h1>
          <p className="text-sm text-slate-400">
            {business.services.length > 0
              ? business.services.map((service) => service.name).join(" · ")
              : "Ask a question or book an appointment"}
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span className="flex items-center gap-2 text-xs text-slate-400">
            <span
              className={`h-2 w-2 rounded-full ${
                voice.state === "listening"
                  ? "bg-emerald-400"
                  : voice.state === "speaking"
                    ? "bg-indigo-400"
                    : voice.state === "thinking"
                      ? "bg-amber-400"
                      : "bg-slate-600"
              }`}
            />
            {STATE_LABEL[voice.state]}
          </span>
          <button
            onClick={() => (active ? voice.stop() : void voice.start())}
            className={`rounded-lg px-4 py-2 text-sm font-medium ${
              active
                ? "bg-rose-500/15 text-rose-300 ring-1 ring-inset ring-rose-500/30"
                : "bg-indigo-500 text-white hover:bg-indigo-400"
            }`}
          >
            {active ? "End call" : "Start voice call"}
          </button>
        </div>
      </header>

      {active && (
        <div className="h-1 overflow-hidden rounded-full bg-slate-800">
          <div
            className="h-full bg-emerald-400 transition-[width] duration-75"
            style={{ width: `${Math.min(100, voice.level * 600)}%` }}
          />
        </div>
      )}

      <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-slate-800 bg-slate-900/60 p-5">
        {turns.map((turn, index) => (
          <div
            key={index}
            className={turn.role === "customer" ? "flex justify-end" : "flex justify-start"}
          >
            <div
              className={`max-w-[80%] rounded-2xl px-4 py-2.5 text-sm ${
                turn.role === "customer"
                  ? "bg-indigo-500 text-white"
                  : "bg-slate-800 text-slate-100"
              }`}
            >
              <p className="whitespace-pre-wrap">{turn.text}</p>
              {turn.intent && (
                <p className="mt-1.5 text-[11px] text-slate-400">routed to: {turn.intent}</p>
              )}
            </div>
          </div>
        ))}
        <div ref={endRef} />
      </div>

      {error && <p className="text-sm text-rose-400">{error}</p>}

      <form onSubmit={sendTyped} className="flex gap-2">
        <input
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder="Can I book a cleaning on Tuesday morning?"
          className="flex-1 rounded-lg border border-slate-700 bg-slate-900 px-4 py-2.5 text-sm text-slate-100 outline-none focus:border-indigo-500"
        />
        <button
          type="submit"
          disabled={sending || !draft.trim()}
          className="rounded-lg bg-indigo-500 px-5 py-2.5 text-sm font-medium text-white hover:bg-indigo-400 disabled:opacity-50"
        >
          Send
        </button>
      </form>
    </div>
  );
}
