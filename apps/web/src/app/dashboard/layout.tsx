import Link from "next/link";
import { OrganizationSwitcher, UserButton } from "@clerk/nextjs";
import { auth } from "@clerk/nextjs/server";

const NAV = [
  { href: "/dashboard", label: "Conversations" },
  { href: "/dashboard/bookings", label: "Bookings" },
  { href: "/dashboard/follow-ups", label: "Follow-ups" },
  { href: "/dashboard/documents", label: "Knowledge" },
  { href: "/dashboard/settings", label: "Settings" },
];

export default async function DashboardLayout({ children }: { children: React.ReactNode }) {
  const { orgId } = await auth();

  return (
    <div className="flex min-h-full flex-1 flex-col">
      <header className="border-b border-slate-800 bg-slate-900/40">
        <div className="mx-auto flex w-full max-w-6xl items-center justify-between gap-4 px-6 py-4">
          <Link href="/dashboard" className="text-lg font-semibold tracking-tight">
            Voxa<span className="text-indigo-400">.</span>
          </Link>
          <div className="flex items-center gap-4">
            <OrganizationSwitcher
              hidePersonal
              afterCreateOrganizationUrl="/dashboard"
              afterSelectOrganizationUrl="/dashboard"
              appearance={{ elements: { rootBox: "text-sm" } }}
            />
            <UserButton />
          </div>
        </div>
        {orgId && (
          <nav className="mx-auto flex w-full max-w-6xl gap-1 px-4 text-sm">
            {NAV.map((item) => (
              <Link
                key={item.href}
                href={item.href}
                className="rounded-t-lg px-3 py-2 text-slate-400 hover:bg-slate-800/50 hover:text-slate-100"
              >
                {item.label}
              </Link>
            ))}
          </nav>
        )}
      </header>

      <main className="mx-auto w-full max-w-6xl flex-1 px-6 py-8">
        {orgId ? (
          children
        ) : (
          <div className="rounded-xl border border-slate-800 bg-slate-900/60 p-8 text-center">
            <h1 className="text-lg font-semibold">Create a business to continue</h1>
            <p className="mx-auto mt-2 max-w-md text-sm text-slate-400">
              Every Voxa receptionist belongs to one business. Use the switcher above to create or
              select an organisation — that is what keeps your calls, documents and bookings
              separate from everyone else&apos;s.
            </p>
          </div>
        )}
      </main>
    </div>
  );
}
