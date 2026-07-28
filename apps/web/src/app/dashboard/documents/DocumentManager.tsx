"use client";

import { useEffect, useRef, useState } from "react";
import { useApi } from "@/lib/useApi";
import type { DocumentUploadResult, VoxaDocument } from "@/lib/types";
import { Badge, Card, EmptyState, formatDateTime } from "@/components/ui";

const ACCEPT = ".pdf,.txt,.md";

function humanSize(bytes: number | null) {
  if (!bytes) return "—";  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export function DocumentManager() {
  const call = useApi();
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<VoxaDocument[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function refresh() {
    setDocuments(await call<VoxaDocument[]>("/api/documents"));
  }

  useEffect(() => {
    call<VoxaDocument[]>("/api/documents")
      .then(setDocuments)
      .catch((cause: Error) => setError(cause.message));
  }, [call]);

  async function upload(file: File) {
    setBusy(true);
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const result = await call<DocumentUploadResult>("/api/documents", {
        method: "POST",
        body,
      });
      setNotice(`Indexed ${result.chunks_indexed} chunks from ${result.document.filename}.`);
      await refresh();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  async function remove(id: string) {
    setBusy(true);
    try {
      await call<void>(`/api/documents/${id}`, { method: "DELETE" });
      await refresh();
    } catch (cause) {
      setError((cause as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-6">
      <Card title="Upload a document">
        <p className="mb-4 text-sm text-slate-400">
          PDF, plain text or markdown, up to 10 MB. The text is split, embedded and stored against
          this business only — no other tenant can retrieve it.
        </p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPT}
          disabled={busy}
          onChange={(event) => {
            const file = event.target.files?.[0];
            if (file) void upload(file);
          }}
          className="block w-full cursor-pointer rounded-lg border border-dashed border-slate-700 bg-slate-900 px-4 py-6 text-sm text-slate-400 file:mr-4 file:rounded-md file:border-0 file:bg-indigo-500 file:px-4 file:py-2 file:text-sm file:font-medium file:text-white hover:file:bg-indigo-400"
        />
        {busy && <p className="mt-3 text-sm text-indigo-300">Indexing…</p>}
        {notice && !busy && <p className="mt-3 text-sm text-emerald-300">{notice}</p>}
        {error && <p className="mt-3 text-sm text-rose-400">{error}</p>}
      </Card>

      <Card title="Indexed documents">
        {!documents ? (
          <EmptyState>Loading…</EmptyState>
        ) : documents.length === 0 ? (
          <EmptyState>
            Nothing uploaded yet. Without documents, every question escalates to a human.
          </EmptyState>
        ) : (
          <ul className="divide-y divide-slate-800">
            {documents.map((document) => (
              <li key={document.id} className="flex items-center justify-between gap-4 py-3">
                <div className="min-w-0">
                  <p className="flex items-center gap-2 truncate text-sm text-slate-200">
                    {document.filename}
                    <Badge value={document.status} />
                  </p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {humanSize(document.byte_size)} · {formatDateTime(document.created_at)}
                  </p>
                  {document.error && (
                    <p className="mt-1 text-xs text-rose-400">{document.error}</p>
                  )}
                </div>
                <button
                  disabled={busy}
                  onClick={() => void remove(document.id)}
                  className="shrink-0 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-400 ring-1 ring-inset ring-slate-700 hover:text-rose-300 disabled:opacity-50"
                >
                  Delete
                </button>
              </li>
            ))}
          </ul>
        )}
      </Card>
    </div>
  );
}
