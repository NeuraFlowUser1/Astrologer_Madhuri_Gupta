# Sarsa Jyotish Sansthan — Project 004

Sarsa's public website introduces Madhuri Gupta and four services: Kundli Matching, Kundli Prediction, Vastu Consultation and Numerology. It uses one public header/footer, simple English with short Hindi lines, illustrated service pages and a Contact page with the owner's Agra address and Google Maps pin.

The public-site implementation and its checks are described in [the public-site guide](docs/public-site-refresh.md). The separate [booking operating guide](docs/appointment-system-release.md) owns booking, staff access, provider connections and recovery. Source implementation, local qualification and actual online release are separate evidence stages; the release record identifies the exact tested and published commit.

## Application boundaries

| Path | Responsibility |
| --- | --- |
| `frontend/src/pages/` | Public pages and the existing appointment form/receipt pages. |
| `frontend/src/site/` | Public frame, reviewed copy, navigation, finite decoration and common booking-state bindings. |
| `frontend/src/contact/` | Enquiry presentation and the existing shared enquiry coordinator. |
| `frontend/src/booking/` | Client-owned appointment presentation, measured scrolling and contained-system adapters. |
| `frontend/scripts/` | Public route generation and release preflight. |
| `frontend/tests/public-site/` | Public-site unit, browser, accessibility, coverage and local performance checks. All application responses are synthetic. |
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
npm --prefix frontend run test:public-site
```

Browser/performance checks and their external report-directory settings are documented in the public-site guide. Native build/proxy helpers are executed and instrumented separately, then merged into the complete source coverage. Tests do not substitute a sample backend for customers.

The Vite development server runs at port 3000 by default. `/api`, `/company` and `/studio` requests use the local Python server on port 8000. Without that server and valid private configuration, unavailable responses are expected. Do not reconnect a retired backend or invent provider credentials to make a local page appear ready.

## Booking and staff access

The saved company settings own prices, available times and verification choices. Booking email is optional while email codes are OFF and required/verified while they are ON. Mobile remains required. Drafts survive tab/app changes; a deliberate page refresh may clear them. Enquiries keep their separate required-email verification flow.

The private pages are `/studio`, `/enquiries-studio`, `/company/booking-control`, `/company/booking-support` and `/company/google-repair`. They retain their existing authentication and internal navigation. Passwords, receipt access, API keys and provider credentials must never be stored in source, screenshots, logs or public documents.

The contained package remains `97ab5d49fc559eb1acdeb7157d4561134d1bad824cca298506f48b2a9d32b49d`: 573 manifest files and migrations 001–036. Dated real payment, Meet, email, spreadsheet and backup acceptance remains in the booking operating guide; public visual checks do not claim fresh provider acceptance.

## Publishing

Use the existing route only: `NeuraFlowUser1/Astrologer_Madhuri_Gupta` → `main` → Vercel `neura-flow1/astrologer-madhuri-gupta` → `https://www.sarsajyotishsansthan.com`.

Vercel stays disconnected from Codex. Publish the same locally qualified commit through Git, then verify its actual public asset identities and read-only page journeys on the official domain. A successful Git push alone does not establish a successful online release. Booking remains ON for this public-site programme; no live price, enquiry, payment or company-setting mutation is required.
