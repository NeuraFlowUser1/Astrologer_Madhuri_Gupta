# Sarsa Jyotish Sansthan — Project 004

## Current website work — 12 October 2026

The About page now adds four supplied certificates after Madhuri's introduction, with short course explanations, full-document previews and an enlarged reader. The preferred AI presentation is used; the yellow certificate's course-name error was corrected against its source, and all originals remain accessible. Existing choreography is preserved, with measured height compensation for root-relative artwork. See [the certificate implementation and focused proof](docs/about-certifications.md).

Reviews now has a public route, shared header/footer entries and one natural Home FAQ link. The old redirect to About is removed. No genuine feedback has been supplied, so the page says “Reviews will be added here”; fictional design accounts remain private and excluded from compiled output. The accepted design is retained for genuine future feedback. See [the Reviews record](docs/testimonials-page.md).

The older `/studio/calendar` address is wired to the existing protected staff handler. Its missing backend export and host rewrite were deterministically diagnosed and repaired. The Booking state-read cancellation investigation is set aside at the owner's request; no guessed timeout or booking-system repair is included. See [the diagnosis](docs/routing-diagnosis-2026-10-12.md).

The historical hosted assessment remains **105/107 cases passing (98.1%)**, not a clean full-suite result. This release uses focused verification only. Actual publication hashes and official-domain observations are recorded in the client study `design-review/2026-10-12-about-certifications/`; a push alone does not prove publication. Booking stays ON and Vercel stays disconnected from Codex.

## Current change — 11 October 2026

The approved name-and-phone booking-details replacement is published, using contained release `54af467afbe152286f1f81f28f904a8b59b51e31111e6a81d93b1d340bd3720a` (576 files; migrations 001–037). The official application, database and existing worker independently report this release. Booking is ON again under the original owner intent. Source publication: `0b4d4e1422bfe731aa527393709124be86d8827b`. These are publication/read-only observations; no real customer lookup or provider acceptance journey was run. Customers use `/booking/receipt` with the full name and phone saved when booking. Old booking-help/access links redirect there. Lookup grants viewing, refresh and a local PDF for a confirmed appointment; it grants no payment, cancellation, rescheduling, email-send or contact-change action. The original saved-browser receipt remains separate. Contact and appointment booking provide the entry links.

Migration 037 retires old code authority in one changeover while preserving audit facts and the existing protected staff correction. Earlier migration files remain unchanged. Sarsa alone receives the agreed visual section/background/navigation/art refinements; its original choreography remains intact. The owner excluded tests and release gates; no fresh test or coverage result is claimed. Necessary website builds and source/rendered-page review are recorded separately.

## Retained earlier release evidence

Sarsa's public website introduces Madhuri Gupta and four services: Kundli Matching, Kundli Prediction, Vastu Consultation and Numerology. Its public appearance builds on the owner-selected checkpoint A from 8 October 2026, with the subsequently approved additive imagery, combined Home chapter, section backgrounds and Google Map. The original animation owners and later shared booking repairs remain. The current public-site guide below owns those refinements; the unrefined checkpoint's map absence is historical.

The public-site implementation and its checks are described in [the public-site guide](docs/public-site-refresh.md). The separate [booking operating guide](docs/appointment-system-release.md) owns booking, staff access, provider connections and recovery. Source implementation, local qualification and actual online release are separate evidence stages; the release record identifies the exact tested and published commit.

## Application boundaries

| Path | Responsibility |
| --- | --- |
| `frontend/src/pages/` | Public pages and the existing appointment form/receipt pages. |
| `frontend/src/site/` | Restored public frame, original choreography and common booking-state bindings. |
| `frontend/src/contact/` | Enquiry presentation and the existing shared enquiry coordinator. |
| `frontend/src/booking/` | Client-owned appointment presentation, measured scrolling and contained-system adapters. |
| `frontend/scripts/` | Public route generation and release preflight. |
| `frontend/tests/public-site/` | Focused restoration unit/browser checks. Coverage is scoped to two retained functional owners; browser application responses are synthetic. |
| `api/index.py` | Existing Python hosting entrypoint. |
| `appointment-system/` | Complete independently contained booking system; no factory runtime dependency. |
| `appointment-settings/` | This installation's public profile and settings contracts. Secrets are stored outside source. |
| `workers/` and `.github/workflows/` | Existing background processing, monitoring and independent backups. |

This programme changes the Sarsa public pages and local frame/scroll integration. AstroAdvice, booking-master bytes, database rules, prices, Google approvals, payment/email contracts, worker configuration and private portal permissions are preserved.

## Local development and checks

Use Node 22 and the committed frontend lockfile:

```sh
npm ci --prefix frontend
npm --prefix frontend run dev
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run check:public-site
npm --prefix frontend run test:restore
```

The public-site guide defines the focused restoration checks and their exact coverage limits. Native build/proxy helpers are exercised separately. Tests use isolated synthetic responses; they do not provide a substitute backend to customers.

The Vite development server runs at port 3000 by default. `/api`, `/company` and `/studio` requests use the local Python server on port 8000. Without that server and valid private configuration, unavailable responses are expected. Do not reconnect a retired backend or invent provider credentials to make a local page appear ready.

## Booking and staff access

The saved company settings own prices, available times and verification choices. Booking email is optional while email codes are OFF and required/verified while they are ON. Mobile remains required. Drafts survive tab/app changes; a deliberate page refresh may clear them. Enquiries keep their separate required-email verification flow.

The private pages are `/studio`, `/enquiries-studio`, `/company/booking-control`, `/company/booking-support` and `/company/google-repair`. They retain their existing authentication and internal navigation. Passwords, receipt access, API keys and provider credentials must never be stored in source, screenshots, logs or public documents.

The contained package is `54af467afbe152286f1f81f28f904a8b59b51e31111e6a81d93b1d340bd3720a`: 576 manifest files and migrations 001–037, matching the current release manifest. Dated real payment, Meet, email, spreadsheet and backup acceptance remains in the booking operating guide; the new read-only hosted checks do not claim fresh provider acceptance.

## Publishing

Use the existing route only: `NeuraFlowUser1/Astrologer_Madhuri_Gupta` → `main` → Vercel `neura-flow1/astrologer-madhuri-gupta` → `https://www.sarsajyotishsansthan.com`.

Vercel stays disconnected from Codex. Publish the same locally qualified commit through Git, then verify its actual public asset identities and read-only page journeys on the official domain. A successful Git push alone does not establish a successful online release. Booking remains ON for this public-site programme; no live price, enquiry, payment or company-setting mutation is required.
