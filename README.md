# Sarsa Jyotish Sansthan — Project 004

This imported client project is being rebuilt around Madhuri Gupta’s personal brand and a permanent appointment-booking system. The current implementation uses React/Vite, FastAPI, Neon Postgres, Razorpay, Google Calendar/Meet, separately owned Google Sheets, Resend and a dedicated Cloudflare recovery worker.

**Current state, 30 September 2026:** the redesigned public frontend and permanent backend are live on the official domain through publication `a9ed73e`. All12 public routes, booking policy/help and the staff shell are accepted. All five private Studio setup checks pass after preserving and reformatting the original Google token key; unsigned status returns401. Both Google owners have connected through Studio, and both separately owned spreadsheets are ready with current consent revisions. Actual appointment/Meet, record delivery and email/payment acceptance remain distinct checks. Both database ledgers are checksum-verified through030. Dedicated Cloudflare Worker `83b28f4b-c203-477b-992c-14037e33424a` retains the15-minute schedule, original four protected settings and existing queue/KV. Its actual scheduled pass and empty-system queue pass succeeded; public health returns200/healthy. Reviewed worker fix and independent monitoring are published as `c529cfc`; the first monitor run passed. Sarsa’s merchant is `ThvGDrQ1FuyLI8`; the owner-created encrypted live settings pass production parsing, but Vercel application, capture/webhook and actual payment acceptance remain pending. No appointment, email, charge or refund was submitted by these checks.

**Backups are live:** the daily encrypted backup workflow is published and active in the existing GitHub repository. Its first production export, isolated restore, Sarsa-owned Google Drive upload and authenticated readback passed; a same-day rerun verified the existing copy without duplication. The schedule is08:32 India time. The owner has saved the recovery key, and actual initial failure notifications reached NeuraFlow’s inbox. See the [backup operating instructions and successful runs](tools/backup/README.md). The first accepted archive covers the earlier019 schema; a backup of the now030 schema has not yet been claimed. Website publication is separately recorded above.

See the [current implementation checkpoint](design-review/2026-09-17/15-automatic-booking-plan/verification.md#website-integration-checkpoint--29-september-2026) for checks and remaining live account actions.

**Deployment follow-up:** the hosted booking page computes `overflow-x:clip` and has no horizontal overflow at390px/320px. Protected diagnostics expose only booleans. Google and payment keys remain private; no existing key was regenerated. Sarsa’s local mail limits are20/day and600/rolling31days, with enquiries limited to8/day and240/rolling31days within those totals. These counters cannot reserve capacity against Project003 or other senders in the shared Resend account. Actual Contact activation, notification delivery, Meet/payment acceptance and final policy review remain.

## Start here

- [Whole-website completion and release plan](design-review/2026-09-17/15-automatic-booking-plan/website-completion-implementation-plan.md) — current planned work, including the newly onboarded Sarsa Razorpay account and all remaining hosted acceptance.

- [Current implementation plan and status](design-review/2026-09-17/15-automatic-booking-plan/permanent-system-execution-plan.md)
- [Permanent resource and account manifest](design-review/2026-09-17/15-automatic-booking-plan/permanent-resource-manifest.md)
- [Verification evidence and outstanding acceptance](design-review/2026-09-17/15-automatic-booking-plan/verification.md)
- [Staff operations and assisted recovery](design-review/2026-09-17/15-automatic-booking-plan/staff-appointment-changes.md)
- [Booking-engine contracts and checks](backend/booking_engine/README.md)
- [Improvements to review for Project003 later](design-review/2026-09-17/15-automatic-booking-plan/004-to-003-improvement-register.md)

## Source layout

| Path | Responsibility |
| --- | --- |
| `frontend/src/pages/` | Actual website pages; Booking and Contact use final same-origin API contracts |
| `frontend/src/booking/`, `frontend/src/contact/` | Customer state, validation, receipt access and motion |
| `api/index.py` | Vercel entry point for the permanent FastAPI application |
| `backend/booking_engine/` | Booking, payment evidence, Google/Resend delivery, protected staff actions and receipt recovery |
| `backend/booking_engine/migrations/` | Immutable, checksum-tracked database changes; never applied during a website request |
| `backend/booking_engine/studio_assets/` | Private `/studio` and public assisted `/booking-help` pages |
| `workers/booking-recovery/` | Dedicated queue processing,15-minute recovery and independent health-monitor source |
| `design-review/2026-09-17/` | Approved HTML directions, choreography, planning and QA evidence |
| `media/` | Client-supplied assets, including the approved Madhuri portrait |
| `tools/` | Protected-setting handoff and encrypted-backup tools; credentials stay out of source and logs |

The imported folder layout is retained. No client restructuring or Project003 modification is implied.

## How the permanent booking system works

The database owns prices, availability, reservations, appointment state and recorded payment evidence. A browser payment success screen cannot confirm an appointment. Both email and mobile are mandatory; booking has no email OTP. Contact enquiries use their separate verification flow.

Saved work drives Google Meet creation, the client’s own spreadsheet, NeuraFlow’s separate spreadsheet, and Resend delivery. A saved booking is distinct from a ready meeting or delivered email. Resend replies go to `sarsajyotish@gmail.com`; the sending identity is the verified Sarsa mail subdomain. No SMTP or Jitsi fallback is part of this implementation.

Practice staff can block time, move/cancel appointments, inspect problems, retry eligible work, review verified full-refund evidence, and correct contact details after the approved callback procedure. Agency access is limited to its own connection and record-copy work. Cancellation does not send a refund. Lost receipt access uses verified phone support and a short-lived activation code; private receipt credentials never enter email or URLs.

## Local checks

From this client root, use an existing Python environment with the declared requirements installed:

```sh
python -m unittest discover -s backend/booking_engine/tests
node --test frontend/tests/routes.test.mjs frontend/tests/booking/*.test.mjs frontend/tests/contact/*.test.mjs workers/booking-recovery/worker.test.mjs
npm run build --prefix frontend
```

`npm run dev --prefix frontend` starts Vite at port3000 by default (it may choose another port if busy). `/api`, `/studio` and `/booking-help` proxy to port8000. Without a correctly configured permanent backend, unavailable-service responses are expected; do not substitute the retired application or sample provider data. Browser test fixtures intercept requests only inside test code.

## Hosting and activation

Sarsa uses the existing Vercel project `astrologer-madhuri-gupta` in the owner’s separate account. The Git repository is `NeuraFlowUser1/Astrologer_Madhuri_Gupta`. Build settings and routing are in `vercel.json`: frontend output is `frontend/dist`; API, Studio and booking-help requests reach `api/index.py`. Do not use the old Render commands or `backend/main.py` as the permanent application entry point.

`main.py` and `backend/main.py` remain imported legacy source. Their obsolete submission routes are retired with410 responses. They are not production setup instructions for this booking engine.

Schedule browsing is independent of Razorpay readiness. Keep the permanent payment and delivery correctness controls; missing payment configuration returns a clear checkout error without an appointment. The production upgrade through030 is complete; finish protected configuration and hosted Google/worker/email/payment checks as separate readiness work. `SARSA_CONTACT_DELIVERY_ENABLED=true` is a deliberate final Contact readiness switch; it also requires every delivery credential and the database intake switch. Existing protected keys must not be regenerated casually. Never put credentials in this repository, chat, logs, frontend variables or documentation.

Privacy and terms are the final content task before public release, as requested. See the current plan for provider, operational and release boundaries.
