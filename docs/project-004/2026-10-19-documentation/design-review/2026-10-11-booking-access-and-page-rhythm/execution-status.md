> Dated GitHub handoff copy, 19 October 2026. The original working document is recorded in manifest.json. Relative links have been adapted for this repository; any unavailable local-only evidence is identified explicitly.

# Approved implementation: completed

Completed 11 October 2026. The shared access change is published on AstroAdvice and Sarsa through their existing main-branch deployment connections. Both separate production databases have migration 037, both existing workers and official applications report the matching release, and both booking switches are effective ON.

| Work | Completed | Result |
| --- | --- | --- |
| Shared master and contained packages | 1 master + 4 package copies | 576 files per package; release `54af467afbe152286f1f81f28f904a8b59b51e31111e6a81d93b1d340bd3720a`. Migrations 001–036 remain unchanged. |
| Shared booking access | 2 of 2 websites | Saved full name + phone; no required booking reference, email or eight-digit code. Read-only history/details, refresh and confirmed-appointment PDF. |
| Code retirement / protected correction | 2 of 2 databases | Migration 037; four usable-code columns removed, old issuer/redeemer signatures absent. Historical audit and protected staff corrections retained. |
| Sarsa visual refinement | Complete | Booking photos/independent ornament, section surfaces, selected/hovered navigation, Contact/Booking lookup entries and footer cleanup. |
| Original choreography | Preserved | Home, About, service-detail and shared scene owners are unchanged. Existing Contact/Services movement geometry/timing is preserved; stationary paint layers add section boundaries. |
| Source and visual review | Complete | [Local rendered evidence](execution-evidence/README.md), five reviewed widths, synthetic empty/list/detail/stale states, and public live form/redirect observations without entering customer details. |
| Website / worker publication | 2 of 2 + 2 of 2 | Existing main branches and existing Cloudflare workers; independent protected application release readbacks match. |
| Owner settings and saved records | Preserved | Both original ON intents restored only while the saved changeover command still won. All seven existing booking records and retained audit facts preserved. |
| Tests / release gates | 0 run | Explicit owner boundary. Necessary packaging builds are separate; no fresh coverage, suite or real-provider acceptance claim. |

## Current user journey

Use “View my booking” on Contact or Book an appointment. `/booking/receipt` is the single details route; old `/booking-help` links and AstroAdvice’s extra `/booking/access` alias replace the current history entry and discard the old query/hash. The Sarsa footer has no recovery link. Both name and phone must match saved facts. A name alone does not bypass a wrong saved phone.

Lookup cannot pay, cancel, reschedule, change contacts or send an email. The existing stronger saved-browser receipt remains independent. Inputs/results stay in memory, with cancellation and clearing on lifecycle/authority changes. Private route metadata and API responses prevent indexing/caching/referrer leakage.

## Evidence and boundaries

The shared programme evidence is in `04-shared-tools/003-appointment-booking-system/001-implementation-evidence/2026-10-11-name-phone-booking-details/`. Source, database, worker, protected application, restored company state and rendered observations are separate records. The migration ran once per registered production database, in one provider transaction using the runner’s exact ledger and 4004001/maintenance/booking lock order, with 2s lock and 30s statement bounds. The provider executor used an invoker wrapper around the exact migration source; the source SHA is in the ordinary migration ledger.

The two local `002-project-working-copies` retain their older website scaffolds and unrelated work. Their complete common packages match the release, and obsolete code-page callers were replaced with the canonical redirect. The current customer site adapters are the two published repositories; this change does not promote the older scaffolds into customer deployments. Original dirty factory/imported/publication work was preserved.

No real-customer lookup, payment, cancellation, refund, customer email, new provider account, full/focused test suite, lint, coverage or release gate was performed. Local sample identities and booking references are invented. Existing protected credentials were decrypted only in memory; none are in publication files.

No unresolved implementation or publication blocker remains. The recommended next step is owner review of the live Sarsa pages on phone and desktop, particularly chapter spacing, navigation emphasis and the new booking artwork. This is a visual preference review; it is not a test gate or a request to renew publication approval.
