import { notFound } from "next/navigation";
import { API_BASE_URL } from "@/lib/api";
import type { PublicBusiness } from "@/lib/types";
import { Receptionist } from "./Receptionist";

export const dynamic = "force-dynamic";

export default async function DemoPage({
  params,
}: {
  params: Promise<{ businessId: string }>;
}) {
  const { businessId } = await params;

  // Unauthenticated on purpose: this is the page a customer would land on.
  const response = await fetch(`${API_BASE_URL}/api/public/businesses/${businessId}`, {
    cache: "no-store",
  });
  if (response.status === 404) notFound();
  if (!response.ok) {
    return (
      <main className="mx-auto w-full max-w-2xl px-6 py-16 text-center text-slate-400">
        The receptionist is unavailable right now.
      </main>
    );
  }

  const business = (await response.json()) as PublicBusiness;

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col px-6 py-10">
      <Receptionist business={business} />
    </main>
  );
}
