import { DocumentManager } from "./DocumentManager";

export default function DocumentsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Knowledge</h1>
        <p className="mt-1 text-sm text-slate-400">
          What Voxa is allowed to answer from. Anything outside these documents becomes a follow-up
          instead of a guess.
        </p>
      </div>
      <DocumentManager />
    </div>
  );
}
