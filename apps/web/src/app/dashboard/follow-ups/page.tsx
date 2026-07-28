import { FollowUpList } from "./FollowUpList";

export default function FollowUpsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Follow-ups</h1>
        <p className="mt-1 text-sm text-slate-400">
          Calls Voxa deliberately did not handle — complaints, refunds, and anything it could not
          ground in your documents.
        </p>
      </div>
      <FollowUpList />
    </div>
  );
}
