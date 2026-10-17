# Sarsa Jyotish Sansthan — Project 004

## Current website work — 17 October 2026

The approved Home/About/logo mockup is implemented in the separate `work/home-about-logo-20261017` branch and `.local-runtime/hero-brand-20261017` worktree. Home has the full Sarsa/by Madhuri identity, Astro wording, confirmed 15+ years, two clear actions and all five service shortcuts. About has a name-led introduction and source-backed experience/studies strip. The approved lotus/kundli logo is shared across public headers with a matching favicon. Original imagery, choreography and all lower content remain. Certificate media/gallery stay removed. See [the full current implementation guide](docs/hero-brand-2026-10-17.md) and [approved design specification](docs/plans/2026-10-17-home-about-logo/approved-design-specification.md).

The compiled Home/About pages match all 16 approved desktop/phone layouts at 320–1920px. Native traces preserve4200/7150ms timing; measured lower About backdrops retain their sizes. The script-free reading view uses the same confirmed facts and existing ON/OFF modes. Production compilation and scoped source checks pass. Runtime source `bd8ecfd42e6d72516e123ad6b9e316dc29004287` is officially published; all ten checked deployed files match the qualified build. The complete [17 October hosted gate](docs/hosted-checks-2026-10-17.md) passes **153/153 unique cases (100%)**,1,558 assertions, 9/9 phases and 0 failures. Actual hosted mockup parity passes 16/16 layouts. Focused checks pass 62/62 with 100% coverage of all ten changed code owners and no exclusions. No owner action remains for this approved programme.

## Active services and previous release evidence — 16 October 2026

Prashna Kundali is added across Home, About, Services and a new six-section service page, with two purpose-made photographs and scoped multi-stage movement. Booking supports ₹1,100 per question, 1–10 questions and one 30-minute Google Meet appointment. **Prashna is enabled in the actual saved service policy.** The direct booking link selects it, the native 1–10 question choices and server totals agree, and the original four service prices remain unchanged. See [the current feature, review and activation guide](docs/prashna-kundali.md).

At the owner's request, About's four certificates/course gallery, reader and active public media are removed. Originals, comparisons and the earlier clean worktree remain intact. The personal introduction leads directly into five service choices, with the original choreography and measured backdrop compensation preserved. See [certificate retirement](docs/about-certifications.md).

Reviews contains the complete accepted five-section page and all twelve accounts confirmed by the owner as legitimate and approved by Madhuri for publication. The original design, exact review wording and choreography are preserved. The shared header/footer and natural Home FAQ link open the same public route; the old redirect to About is removed. Focused proof and publication readback are in [the Reviews record](docs/testimonials-page.md).

The older `/studio/calendar` address is wired to the existing protected staff handler. Its missing backend export and host rewrite were deterministically diagnosed and repaired. The Booking state-read cancellation investigation is set aside at the owner's request; no guessed timeout or booking-system repair is included. See [the diagnosis](docs/routing-diagnosis-2026-10-12.md).

The previous owner-authorized [16 October hosted release gate](docs/hosted-checks-2026-10-16.md) passes **151/151 unique cases (100%)** across all nine phases, with 1,390 assertions and zero blocked/attempted unsafe requests. Both earlier attempts and the test-expectation/image-lifecycle corrections are retained; no product code changed during gate closeout. The12 October 105/107 result is historical. Initial implementation used no tests; the later explicit hosted-gate instruction superseded that boundary for this run. No entire local suite or real provider/customer transaction was run. Actual publication identities and evidence remain in client `design-review/2026-10-16-prashna-implementation/` and `design-review/2026-10-16-prashna-hosted-gate/`. Booking stays ON and Vercel stays disconnected from Codex.

## Current change — 11 October 2026

The approved name-and-phone booking-details replacement is published, using contained release `54af467afbe152286f1f81f28f904a8b59b51e31111e6a81d93b1d340bd3720a` (576 files; migrations 001–037). The official application, database and existing worker independently report this release. Booking is ON again under the original owner intent. Source publication: `0b4d4e1422bfe731aa527393709124be86d8827b`. These are publication/read-only observations; no real customer lookup or provider acceptance journey was run. Customers use `/booking/receipt` with the full name and phone saved when booking. Old booking-help/access links redirect there. Lookup grants viewing, refresh and a local PDF for a confirmed appointment; it grants no payment, cancellation, rescheduling, email-send or contact-change action. The original saved-browser receipt remains separate. Contact and appointment booking provide the entry links.

Migration 037 retires old code authority in one changeover while preserving audit facts and the existing protected staff correction. Earlier migration files remain unchanged. Sarsa alone receives the agreed visual section/background/navigation/art refinements; its original choreography remains intact. The owner excluded tests and release gates; no fresh test or coverage result is claimed. Necessary website builds and source/rendered-page review are recorded separately.

## Retained earlier release evidence

Sarsa's public website introduces Madhuri Gupta and five services: Kundli Matching, Kundli Prediction, Vastu Consultation, Numerology and Prashna Kundali. Saved booking activation is separately recorded above. Its public appearance builds on the owner-selected checkpoint A from 8 October 2026, with the subsequently approved additive imagery, combined Home chapter, section backgrounds and Google Map. The original animation owners and later shared booking repairs remain. The current public-site guide below owns those refinements; the unrefined checkpoint's map absence is historical.

The public-site implementation and its checks are described in [the public-site guide](docs/public-site-refresh.md). The separate [booking operating guide](docs/appointment-system-release.md) owns booking, staff access, provider connections and recovery. Source implementation, local qualification and actual online release are separate evidence stages; the release record identifies the exact tested and published commit.

## Application boundaries

| Path | Responsibility |
| --- | --- |
| `frontend/src/pages/` | Public pages and the existing appointment form/receipt pages. |
| `frontend/src/site/` | Restored public frame, original choreography and common booking-state bindings. |
| `frontend/src/contact/` | Enquiry presentation and the existing shared enquiry coordinator. |
| `frontend/src/booking/` | Client-owned appointment presentation, measured scrolling and contained-system adapters. |
| `frontend/scripts/` | Public route generation and release preflight. |
| `frontend/tests/public-site/` | Focused restoration unit/browser checks. Focused configurations declare their owners explicitly; the Home/About configuration covers every changed code owner without exclusions. Local fixtures are test-only; the hosted runner uses actual responses. |
| `api/index.py` | Existing Python hosting entrypoint. |
| `appointment-system/` | Complete independently contained booking system; no factory runtime dependency. |
| `appointment-settings/` | This installation's public profile and settings contracts. Secrets are stored outside source. |
| `workers/` and `.github/workflows/` | Existing background processing, monitoring and independent backups. |

This programme changes only Sarsa public presentation and its client-owned service/route/media configuration. AstroAdvice, contained booking bytes, database rules, existing four fees, Google approvals, payment/email contracts, worker and private permissions are preserved. The approved new-service settings addition must use the existing protected endpoint and latest revision.

## Local development and checks

The commands below document existing local tools. The current Home/About programme runs focused tests/coverage, targeted lint and necessary compilation, with the complete actual hosted read-only gate after publication. It does not run the entire local suite. [The current implementation guide](docs/hero-brand-2026-10-17.md) and [hosted report](docs/hosted-checks-2026-10-17.md) distinguish these results; older gate evidence remains dated.

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

Vercel stays disconnected from Codex. Publish the same locally qualified commit through Git, then verify its actual public asset identities and read-only page journeys on the official domain. A successful Git push alone does not establish a successful online release. Booking remains ON. The owner completed the single approved protected Prashna addition after website publication. Public policy, native choices and server totals confirm activation. No further service-setting save is pending. Do not overwrite the full saved document from bootstrap.
