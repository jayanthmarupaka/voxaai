import { SettingsForm } from "./SettingsForm";

export default async function SettingsPage({
  searchParams,
}: {
  searchParams: Promise<{ google?: string }>;
}) {
  const { google } = await searchParams;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="mt-1 text-sm text-slate-400">
          Opening hours and service durations are enforced before anything is written to a
          calendar, so they are worth getting right.
        </p>
      </div>
      <SettingsForm googleResult={google} />
    </div>
  );
}
