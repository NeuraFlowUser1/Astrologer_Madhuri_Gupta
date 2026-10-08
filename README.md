> **Current booking release — 8 October 2026:** use [the current operating guide](docs/appointment-system-release.md).
> The complete contained package is `1ec326e28d610bcde53508984612b4346df130579861ff5f190c42c4960de800`, with573 manifest files and migrations001–036. Local booking-only qualification passes. Sarsa source, saved-data upgrade, background service and backup jobs are complete. Its website deployment is pending and booking stays OFF until the remaining live checks finish.
> Booking email follows the email-code switch. Drafts survive tab/app changes; deliberate refresh may clear them. Shared selectors and receipt/Meet/PDF/requested-email behavior are contained in this project. AstroAdvice birth date is optional; Sarsa keeps its own concise four-step appearance.
> Five private pages have internal links with existing sign-in checks. Company credentials are stored encrypted outside source. All three approved software security checks report0 known advisories.
> Preserve existing prices, hours, lengths, verification choices, Google resources and secrets. Both Vercel accounts remain disconnected. Fresh real no-email payments and deliberate email-copy sends are not claimed. Broader website testing and visible note history remain deferred.
> The imported README below is historical reference. Removed backend/worker/setup paths and old commands are not current instructions. Use the operating guide above.

# Sarsa Jyotish Sansthan — Project 004

This imported client project is being rebuilt around Madhuri Gupta’s personal brand and a permanent appointment-booking system. The current implementation uses React/Vite, FastAPI, Neon Postgres, Razorpay, Google Calendar/Meet, separately owned Google Sheets, Resend and a dedicated Cloudflare recovery worker.

**Current state, 30 September 2026, 17:50 UTC:** the redesigned website and permanent backend are live. Staff setup, both separately owned Google spreadsheets, scheduled recovery and the independent monitor have passed their recorded checks. Razorpay settings are recognised on the live website; the owner saved the webhook and selected automatic capture. Normal booking and enquiry intake are now enabled after guarded readiness checks. The approved prices and available times are served correctly. The owner’s real Contact test passed: verification, acknowledgement and practice-notice emails have delivery reports; both separately owned spreadsheet jobs completed once with the correct Project004 label. The owner’s real1 INR booking is confirmed with captured payment, signed callback processing, Google Meet, both record copies and three delivered booking emails. Normal prices are fully restored in source, the actual deployment and the database; fresh checkout-context and availability checks pass, and the existing test payment remains1 INR. The real staff reschedule also passed: revision2 at the new time, old slot released, new meeting and record copies, and three delivered update emails. The real cancellation also passed: revision3 cancelled, slot released, meeting cancelled, record copies and cancellation emails delivered. The full1 INR refund is verified in Razorpay and recorded through its signed callback on the first processing attempt. The provider-verified refund review is closed through one authenticated staff action. Final privacy wording is deployed and its actual asset is verified. The owner reports the independent simultaneous-booking check passed, and separate development cleanup verification found no remaining test rows. Assisted-access live acceptance remains an owner/staff-operated check. Client dashboard/account-choice/date-picker redesign is separately deferred and recorded. No appointment, message, charge or refund was created by Codex in these checks.

**Backups are live:** the daily encrypted backup workflow is published and active in the existing GitHub repository. Its first production export, isolated restore, Sarsa-owned Google Drive upload and authenticated readback passed; a same-day rerun verified the existing copy without duplication. The schedule is08:32 India time. The owner has saved the recovery key, and actual initial failure notifications reached NeuraFlow’s inbox. See the backup operating instructions and successful runs (historical path `tools/backup/README.md`). The first accepted archive covers the earlier019 schema; a backup of the now030 schema has not yet been claimed. Website publication is separately recorded above.

See the [current implementation checkpoint](design-review/2026-09-17/15-automatic-booking-plan/verification.md#website-integration-checkpoint--29-september-2026) for checks and remaining live account actions.

**Deployment follow-up:** the hosted booking page computes `overflow-x:clip` and has no horizontal overflow at390px/320px. Protected diagnostics expose only booleans. Google and payment keys remain private; no existing key was regenerated. Sarsa’s local mail limits are20/day and600/rolling31days, with enquiries limited to8/day and240/rolling31days within those totals. These counters cannot reserve capacity against Project003 or other senders in the shared Resend account. Actual Contact activation, notification delivery, Meet/payment acceptance and final policy review remain.

## Start here

- [Whole-website completion and release plan](design-review/2026-09-17/15-automatic-booking-plan/website-completion-implementation-plan.md) — current planned work, including the newly onboarded Sarsa Razorpay account and all remaining hosted acceptance.

- [Current implementation plan and status](design-review/2026-09-17/15-automatic-booking-plan/permanent-system-execution-plan.md)
- [Permanent resource and account manifest](design-review/2026-09-17/15-automatic-booking-plan/permanent-resource-manifest.md)
- [Verification evidence and outstanding acceptance](design-review/2026-09-17/15-automatic-booking-plan/verification.md)
- [Staff operations and assisted recovery](design-review/2026-09-17/15-automatic-booking-plan/staff-appointment-changes.md)
- Booking-engine contracts and checks (historical path `backend/booking_engine/README.md`)
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

Privacy, terms and booking-policy wording describe the completed connections, separate enquiry verification, protected browser access and encrypted backups. The reviewed policy update is published and the actual deployed asset is verified. See the [operating handover](design-review/2026-09-17/15-automatic-booking-plan/operating-handover.md) for staff routines and unresolved acceptance boundaries.
