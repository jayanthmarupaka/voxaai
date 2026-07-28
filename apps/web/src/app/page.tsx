import Link from "next/link";
import { Show, SignInButton, SignUpButton, UserButton } from "@clerk/nextjs";

const FEATURES = [
  {
    title: "Answers the phone",
    body: "Speech in, speech out, over a websocket. Whisper transcribes, Piper speaks, and the caller can interrupt mid-sentence.",
  },
  {
    title: "Books into a real calendar",
    body: "Availability is checked against Google Calendar and your opening hours before anything is written. No double bookings.",
  },
  {
    title: "Answers from your own documents",
    body: "Upload a menu or a price list. Answers are grounded in your text only — if it isn't in there, the call goes to a human.",
  },
  {
    title: "Knows when to give up",
    body: "Complaints, refunds and anything it can't ground get logged as a follow-up task with a transcript, not improvised.",
  },
];

export default function Home() {
  return (
    <main className="flex-1">
      <header className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-6">
        <span className="text-lg font-semibold tracking-tight">
          Voxa<span className="text-indigo-400">.</span>
        </span>
        <nav className="flex items-center gap-3 text-sm">
          <Show when="signed-out">
            <SignInButton mode="modal">
              <button className="rounded-lg px-3 py-1.5 text-slate-300 hover:text-white">
                Sign in
              </button>
            </SignInButton>
            <SignUpButton mode="modal">
              <button className="rounded-lg bg-indigo-500 px-3 py-1.5 font-medium text-white hover:bg-indigo-400">
                Get started
              </button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <Link
              href="/dashboard"
              className="rounded-lg bg-indigo-500 px-3 py-1.5 font-medium text-white hover:bg-indigo-400"
            >
              Dashboard
            </Link>
            <UserButton />
          </Show>
        </nav>
      </header>

      <section className="mx-auto w-full max-w-5xl px-6 pb-16 pt-10">
        <p className="text-sm font-medium text-indigo-400">AI receptionist</p>
        <h1 className="mt-3 max-w-2xl text-4xl font-semibold tracking-tight sm:text-5xl">
          Small businesses miss calls. Voxa doesn&apos;t.
        </h1>
        <p className="mt-5 max-w-2xl text-lg text-slate-400">
          A dental practice loses a patient every time the phone rings during a procedure. Voxa
          picks up, answers questions from the practice&apos;s own documents, books the appointment
          into the real calendar, and flags anything it shouldn&apos;t handle alone.
        </p>
        <div className="mt-8 flex flex-wrap gap-3">
          <Show when="signed-out">
            <SignUpButton mode="modal">
              <button className="rounded-lg bg-indigo-500 px-5 py-2.5 font-medium text-white hover:bg-indigo-400">
                Create your receptionist
              </button>
            </SignUpButton>
          </Show>
          <Show when="signed-in">
            <Link
              href="/dashboard"
              className="rounded-lg bg-indigo-500 px-5 py-2.5 font-medium text-white hover:bg-indigo-400"
            >
              Go to dashboard
            </Link>
          </Show>
        </div>

        <dl className="mt-16 grid gap-6 sm:grid-cols-2">
          {FEATURES.map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-slate-800 bg-slate-900/60 p-5"
            >
              <dt className="font-medium text-slate-100">{feature.title}</dt>
              <dd className="mt-2 text-sm leading-relaxed text-slate-400">{feature.body}</dd>
            </div>
          ))}
        </dl>
      </section>
    </main>
  );
}
