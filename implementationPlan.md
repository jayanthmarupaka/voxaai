# Voxa — AI Voice Receptionist for Small Businesses
### Implementation Plan for Coding Agent

## Problem Statement

Small business owners (dentists, salons, consultants, repair shops)
lose bookings every day because they can't answer calls or chat while
serving a client, and can't afford a receptionist. Generic chatbots
don't solve this — they answer FAQs but can't actually book anything,
and they don't know the business's real pricing/policies.

Voxa is an embeddable-style voice assistant a business puts in front of
customers. Customers talk to it naturally to book appointments, ask
business-specific questions, or leave a request for a callback — and
the business owner gets a dashboard to manage it all.

## Core Features

**Customer-facing (voice demo page)**
1. Real-time voice conversation (speak, get spoken responses — full duplex)
2. Book/reschedule/cancel appointments — checks real calendar
   availability, respects business hours, avoids double-booking
3. Answer business-specific questions accurately — RAG over documents
   the owner uploads (pricing sheets, FAQs, policies), not generic web
   search
4. Escalate what it can't handle — captures the customer's question +
   contact info as a follow-up task instead of guessing
5. Booking confirmation via SMS (Twilio) and/or email (SendGrid) sent
   to the customer after a successful booking

**Owner-facing (dashboard)**
6. Sign up / log in, connect Google Calendar
7. Upload/manage business documents (used for RAG)
8. Set business hours, services, and a custom greeting for the assistant
9. Live conversation feed — see transcripts of what customers asked in
   real time
10. Follow-up queue — see and resolve escalated customer requests

**Explicitly out of scope for this version** (see Resolved Decisions
below): a true embeddable `<script>` widget, multi-language support,
analytics dashboard, persona customization beyond name/greeting.

## Architecture

```
┌─────────────────────────┐
│  Voice Demo Page          │  (Next.js/TS, mic capture via WebRTC,
│  /demo/[businessId]       │   public, no auth required)
└────────────┬─────────────┘
             │ WebSocket (audio stream)
             ▼
┌─────────────────────────────────────────────────────────┐
│                     FastAPI Backend                       │
│  ┌───────────┐   ┌────────────────────────────────────┐  │
│  │  STT       │──▶│      Router/Orchestrator Agent       │  │
│  │ (Deepgram, │   │  (LangGraph — classifies intent,     │  │
│  │  streaming)│   │   routes to the right tool)           │  │
│  └───────────┘   └───────────────┬───────────────────────┘  │
│              ┌────────────────────┼────────────────────┐    │
│              ▼                    ▼                    ▼    │
│      ┌───────────────┐  ┌──────────────────┐  ┌────────────┐│
│      │ Calendar Agent │  │   RAG Agent        │  │ Escalation ││
│      │ (Google        │  │ (pgvector search   │  │   Agent    ││
│      │  Calendar API) │  │  over biz docs)     │  │ (task queue)││
│      └───────────────┘  └──────────────────┘  └────────────┘│
│              └────────────────────┼────────────────────┘    │
│                                   ▼                          │
│                          response_compiler                   │
│                                   │                          │
│                            TTS (ElevenLabs/                  │
│                             OpenAI TTS)                      │
└───────────────┬───────────────────────────────────────────┘
                 │ WebSocket (audio back)
                 ▼
          Customer hears reply
                 │
                 ▼
     Twilio SMS / SendGrid email
        (booking confirmation)

┌─────────────────────────────┐
│   Owner Dashboard (Next.js)   │──▶ Clerk auth (multi-tenant: 1 org = 1 business)
│  docs upload · calendar link  │──▶ REST + WebSocket to backend for live feed
│  live feed · follow-up queue  │
└───────────────────────────────┘

           PostgreSQL (+ pgvector extension)
  businesses · users · documents/embeddings · conversations
        · bookings · follow_up_tasks
        (every table scoped by business_id — strict tenant isolation)
```

**Why pgvector instead of a separate vector DB**: already running
Postgres for relational data (businesses, bookings, tasks) — adding the
pgvector extension keeps the stack at one database instead of two.

## Technology Stack

| Layer | Tech | Purpose |
|---|---|---|
| Customer voice page | Next.js + TypeScript, WebRTC/MediaRecorder | embeddable-style voice UI |
| Owner dashboard | Next.js + TypeScript (same app, different routes/auth) | docs, calendar, live feed |
| Real-time transport | WebSockets | full-duplex audio streaming |
| STT | Deepgram (streaming) | speech-to-text |
| TTS | ElevenLabs or OpenAI TTS (streamed) | voice response |
| Orchestration | LangGraph | intent routing across tools |
| LLM | Azure OpenAI GPT-4.1 | reasoning, RAG answer generation |
| Calendar | Google Calendar API | real booking/availability |
| Notifications | Twilio (SMS), SendGrid (email) | booking confirmations |
| Database | PostgreSQL + pgvector | relational data + embeddings, one DB |
| Backend | FastAPI | API + WebSocket server |
| Auth | Clerk (multi-tenant/org support) | business account isolation |
| Deployment | Docker + Fly.io/Render, GitHub Actions | cloud-native, CI/CD pipeline |

## Project Summary

Voxa is a two-sided voice AI product:
- **Customer side**: a standalone voice demo page where a customer talks
  to an AI receptionist that can book/reschedule appointments, answer
  business-specific questions (via RAG over the business's own docs),
  and escalate anything it can't handle.
- **Owner side**: an authenticated dashboard where a business owner
  connects their calendar, uploads documents, configures the assistant,
  and monitors live conversations and follow-up requests.

**Core engineering challenge**: a LangGraph router/orchestrator agent
that classifies customer intent in real time and routes to the correct
tool (Calendar, RAG/knowledge, or Escalation) — not a single-purpose
bot.

## Resolved Decisions

| Decision | Choice | Why |
|---|---|---|
| Business vertical | Generic/configurable — no hardcoded vertical; business hours, services, and docs are all owner-configured | keeps the product reusable, avoids baking vertical-specific logic into the core |
| Booking confirmations | Included — Twilio (SMS) and/or SendGrid (email) after a successful booking | real utility feature, not just a tech checkbox |
| Widget delivery | Standalone demo page for now (`/demo` route in the Next.js app), not a true embeddable `<script>` widget | keeps scope realistic for 1-2 weeks; note in README as a clear "v2" roadmap item |
| Vector store | pgvector extension inside the same PostgreSQL instance | avoids a second database just for embeddings |
| Timeline | 1-2 weeks, evenings | drives the week-by-week task split below |

**Constraints for the agent building this**:
- Keep tenant isolation strict from day one — every DB query involving
  documents, bookings, or conversations must be scoped to the
  authenticated business's ID. Do not defer multi-tenancy to "later."
- The Router/Orchestrator must be an explicit LangGraph graph with
  visible conditional edges (Calendar / RAG / Escalation), not a single
  prompt doing everything — this mirrors the RepoPilot pattern and is
  the core thing being demonstrated.
- All calendar writes (create/update/cancel) must first check
  availability and business hours before booking — never double-book.
- LLM provider is Azure OpenAI GPT-4.1 only.
- Secrets (Google OAuth, Deepgram, ElevenLabs/OpenAI TTS, Twilio/SendGrid,
  Azure OpenAI, Clerk) all via environment variables — never hardcoded.

---

## Week 1 — Foundations: auth, data model, calendar, basic voice loop

### Task 1 — Project scaffold
- [ ] Next.js + TypeScript app (`apps/web`) with two route groups:
      `/dashboard/*` (owner, authenticated) and `/demo/*` (customer-facing,
      public per-business demo page).
- [ ] FastAPI backend (`apps/api`) for REST + WebSocket endpoints.
- [ ] PostgreSQL with `pgvector` extension enabled; set up a migration
      tool (Alembic).
- [ ] Docker Compose for local dev (web, api, postgres).
- [ ] `.env.example` covering all secrets listed in the constraints above.

**Definition of done**: `docker compose up` runs all three services;
Next.js home page and FastAPI `/health` both reachable locally.

### Task 2 — Data model
- [ ] Schema/tables: `businesses` (id, name, hours config, greeting),
      `users` (owner accounts, linked to a business via Clerk org),
      `documents` (business_id, filename, content, embedding via
      pgvector), `conversations` (business_id, transcript, started_at),
      `bookings` (business_id, customer info, time slot, status),
      `follow_up_tasks` (business_id, customer info, question, status).
- [ ] Alembic migration creating all tables with proper foreign keys
      scoped to `business_id`.

**Definition of done**: migrations run cleanly against a fresh
Postgres instance; every table with business-specific data has a
`business_id` foreign key.

### Task 3 — Auth and multi-tenancy
- [ ] Integrate Clerk with organization support — one Clerk org maps
      to one `businesses` row.
- [ ] Owner dashboard routes require authentication; all API calls from
      the dashboard carry the business ID derived from the authenticated
      session, never from a client-supplied parameter.
- [ ] Public `/demo/[businessId]` page requires no auth (customer-facing).

**Definition of done**: two test business accounts can be created,
each owner only ever sees their own business's data — verify by
attempting (and failing) to fetch another business's documents/bookings
via the API directly.

### Task 4 — Google Calendar integration
- [ ] OAuth flow for the owner to connect their Google Calendar from
      the dashboard.
- [ ] Backend functions: check availability against business hours,
      create a booking, reschedule, cancel — all validated against
      real calendar free/busy data before writing.
- [ ] Store the connected calendar's refresh token securely per business.

**Definition of done**: from a test script (not yet wired to voice),
you can check availability and create a real event on a connected test
Google Calendar.

### Task 5 — Basic voice loop (no orchestration yet)
- [ ] WebSocket endpoint accepting streamed audio from the browser.
- [ ] Wire Deepgram streaming STT — confirm live transcripts appear.
- [ ] Wire TTS (ElevenLabs or OpenAI TTS) — confirm a hardcoded response
      streams back as audio the browser can play.
- [ ] Minimal `/demo` page: mic button, live transcript display, audio
      playback of the response.

**Definition of done**: you can speak into the demo page and hear a
hardcoded canned response spoken back — proves the audio pipeline
end-to-end before adding any intelligence.

**Week 1 checkpoint**: auth + data model + calendar integration + raw
voice loop all work independently. Nothing is orchestrated yet — that's
Week 2.

---

## Week 2 — Orchestration, RAG, escalation, dashboard, notifications

### Task 6 — Document upload + RAG pipeline
- [ ] Owner dashboard: upload documents (PDF/text) for their business.
- [ ] Backend: chunk, embed, and store in `documents` table via pgvector.
- [ ] RAG query function: given a customer question, retrieve relevant
      chunks scoped to that business only, generate an answer via Azure
      OpenAI GPT-4.1.

**Definition of done**: uploading a sample pricing doc and asking a
related question via a test script returns an accurate, grounded answer
— and a similarly-worded question against a *different* business's docs
returns nothing (tenant isolation holds for RAG too).

### Task 7 — Router/Orchestrator agent (LangGraph)
- [ ] LangGraph state graph: `START → intent_router → {calendar_agent |
      rag_agent | escalation_agent} → response_compiler → END`.
- [ ] `intent_router` node: classifies the transcript into one of the
      three categories (or a combination, if the design allows follow-up
      turns) using Azure OpenAI GPT-4.1.
- [ ] `calendar_agent` node: wraps Task 4's calendar functions, handles
      multi-turn slot-filling (e.g. "Thursday afternoon" → confirm exact
      time before booking).
- [ ] `rag_agent` node: wraps Task 6's RAG pipeline.
- [ ] `escalation_agent` node: writes a `follow_up_tasks` row with the
      customer's question and any contact info captured.
- [ ] `response_compiler` node: turns whichever agent's output into a
      natural spoken response string to send to TTS.

**Definition of done**: run at least 3 test conversations end-to-end
via the CLI/test harness — one that books, one that gets answered from
docs, one that escalates — confirming the router picks correctly each
time.

### Task 8 — Wire orchestration into the live voice loop
- [ ] Replace the Task 5 hardcoded response with a real call into the
      Task 7 graph, using the live STT transcript as input and streaming
      the graph's response text into TTS.
- [ ] Persist each conversation (full transcript + outcome) to the
      `conversations` table, scoped to the business ID from the demo
      page URL.

**Definition of done**: a full live voice conversation on `/demo/[id]`
results in either a real calendar booking, a grounded answer, or a
logged follow-up task — and the conversation is saved.

### Task 9 — Booking confirmations (Twilio/SendGrid)
- [ ] After a successful booking, send an SMS (Twilio) and/or email
      (SendGrid) confirmation to the customer, using contact info
      captured during the conversation.
- [ ] Handle the case where the customer didn't provide contact
      info — degrade gracefully, don't block the booking.

**Definition of done**: a real test booking triggers a real SMS or
email to a test number/address.

### Task 10 — Owner dashboard: live feed + follow-up queue
- [ ] Live conversation feed: list recent conversations for the
      authenticated business, with transcript and outcome (booked /
      answered / escalated).
- [ ] Follow-up queue: list open `follow_up_tasks`, allow the owner to
      mark them resolved.
- [ ] Basic settings page: business hours, greeting text, connected
      calendar status, uploaded documents list.

**Definition of done**: an owner can log in, see real conversations
from Task 8 testing, and resolve a follow-up task.

### Task 11 — Deployment + CI/CD
- [ ] Dockerize both `apps/web` and `apps/api` for production.
- [ ] Deploy to Fly.io or Render (with managed Postgres add-on).
- [ ] GitHub Actions: lint + basic tests on push, deploy on merge to
      main.

**Definition of done**: a real public URL exists where the `/demo` page
and dashboard both work against the deployed backend.

### Task 12 — README and portfolio polish
- [ ] Architecture diagram, problem statement, and the "why this
      design" rationale (multi-tenant RAG, explicit router graph,
      calendar-before-booking validation).
- [ ] Demo video/GIF of a full voice conversation resulting in a real
      booking.
- [ ] Clear "v2 roadmap" section noting the true-embeddable-widget
      cut, and any other stretch features not built.

**Definition of done**: a stranger reading the README understands the
product, why it's architected this way, and can see proof it works.

---

## Suggested weekly split

**Week 1 (evenings)**: Tasks 1 → 5 — foundations, nothing intelligent yet.
**Week 2 (evenings)**: Tasks 6 → 12 — orchestration, RAG, live integration, deploy.

**If time runs short**: cut Task 9 (notifications) and Task 10's
settings page first — a working voice loop with real booking + RAG +
escalation, deployed with a basic dashboard feed, is already a complete
and demoable product. Notifications and settings polish can be
"v1.1" in the README roadmap.