# Self-Context — EXAMPLE / Template

> **Purpose:** This file lets `/research` and `/deep-research` tailor their output to YOUR specific stack, projects, and operating mode. Without it, both skills still work but produce more generic output. The skills load this file conditionally at Step 0.5 and gracefully degrade if it's missing.
>
> **To use:** copy this file to `_research-lib/contexts/self.md` (which is gitignored — your personal version stays local) and fill in your real details. The skills look for `self.md` automatically.

---

## Who I am

**Name / handle:** {{your-handle}}
**Role:** {{e.g., "Solo dev shipping SaaS for X niche" / "Engineering lead at Y company" / "Researcher in Z domain"}}
**Operating mode:** {{e.g., "Single-developer machine, no enterprise security tooling, fast iteration, internal-tool tolerance differs from commercial-app tolerance"}}

## Active projects / portfolio

List the apps, products, or projects you currently maintain. For each, note the relevant tech and any project-specific constraints.

- **{{Project name}}** — {{one-line description}}. Stack: {{Next.js / Supabase / Stripe / etc.}}. Constraint: {{commercial vs internal / paying customers / etc.}}
- **{{Project name}}** — ...

## Tech stack (what you actually use)

| Layer | Tech |
|---|---|
| Frontend | {{e.g., Next.js 15, Vite + React 18, Tailwind, shadcn/ui}} |
| Backend | {{e.g., Next.js API routes, Edge Functions, Cloud Functions}} |
| Data | {{e.g., Supabase Postgres + RLS, Firebase Firestore}} |
| Auth | {{e.g., Supabase Auth, Firebase Auth, Clerk}} |
| Hosting | {{e.g., Vercel, Netlify, Fly.io}} |
| Payments | {{Stripe / Lemon Squeezy / N/A}} |
| Email | {{Resend / Postmark / SendGrid / N/A}} |
| Analytics | {{PostHog / Plausible / Mixpanel / N/A}} |
| AI / LLM | {{Anthropic / OpenAI / Google / etc.}} |

## What you are NOT exposed to

The skills use this for **non-exposure detection** — when a CVE or security advisory hits a tech you don't use, `/deep-research` will explicitly say "you do NOT use X — not affected." Saves a lot of noise.

- {{e.g., "AWS — not on the stack"}}
- {{e.g., "Kubernetes — single-machine deploys, irrelevant"}}
- {{e.g., "MongoDB — Postgres only"}}
- {{e.g., "React Native / mobile — web only"}}

## Decision preferences

How you make calls — used by the skills to phrase recommendations in your style.

- **Risk tolerance:** {{e.g., "internal tools can move fast; commercial app is bias-to-safe"}}
- **Refactor scope:** {{e.g., "no premature abstraction; natural decomposition only when seams exist"}}
- **Confirmation gate:** {{e.g., "show me destructive SQL before running"}}
- **Time framing:** {{e.g., "estimate in Claude-time, not human-developer-time"}}

## Communication style

- {{e.g., "Direct disagreement preferred over hedging"}}
- {{e.g., "Concrete options, not open-ended prompts"}}
- {{e.g., "Evidence over assertion; admit uncertainty"}}
- {{e.g., "Narrate progress as you work"}}

---

## How the skills use this file

- **`/research`** — at Step 0.5, decides whether the topic is "self-applied" (concerns your stack/projects) or generic. If self-applied, tailors recommendations to your actual stack. If generic, ignores most of this and produces a neutral report.

- **`/deep-research`** — at Step 0.5, loads this file as the canonical source of your stack for exposure analysis. Maps CVEs and advisories against your `Tech stack` and explicitly notes non-exposure against `What you are NOT exposed to`.

- **`/content-research`** — does NOT load this file (entity archives don't need personal framing).

If this file is missing, skills note "self-context unavailable" in the report's `gaps` frontmatter field and proceed generically.
