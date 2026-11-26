# Contained appointment and enquiry system

This package is the neutral master for independently owned project copies. Identity, business policy, accounts, website content and protected values belong to the installing project. The package cannot select another project or load a factory runtime.

## Current implementation status

The common foundation includes the approved booking-experience refinements: draft retention through tab checks, V3 optional email, accessible date/time controls, shared receipt facts/PDF/requested email copy, and thin receiving-site adapters. Migration 037 adds read-only booking access using the saved full name and phone number, with bounded history, refreshed appointment facts and confirmed-appointment PDFs. It retires the customer code process while retaining historical audit facts and protected staff contact correction. The [booking-details contract](docs/booking-details.md) defines matching, admission, privacy, browser lifetime and the single changeover; the [booking-experience contract](docs/booking-experience.md) continues to cover checkout and original saved receipts.

The historical saved-name/phone change was implemented under its dated no-tests/no-release-gates instruction. That is separate from the currently approved automation qualification. Standard release 1.0.2-rc.1 adds [explicit production-branch metadata and workflow/runtime guards](docs/production-branch.md): version 1 retains main-only behaviour and version 2 requires its declared branch. Existing engine, SQL migrations, worker contracts, account ownership and saved business policy are unchanged. Matching source-bound qualification records own the current test/coverage and publication status; earlier evidence is carried only for byte-identical owners.

## Project folder contract

Keep `appointment-system/` and `appointment-settings/` as siblings inside the actual project repository. The settings folder contains `project.json` and `business-settings.json`; protected values are supplied only through that project's own account/environment. The serving entry verifies `release.json` once before importing provider composition, binds only its sibling settings and requires a fresh process for identity changes.

`project.json` declares installation, project, environment, official origin/aliases, independent database targets, approved owners, sender, providers, worker and the classified website surfaces. Basic commercial settings are separate from protected connections and internal retry parameters. The migration target is a declared direct owner connection, separate from the six routine purpose connections.

## Authority and the service switch

The company enters through username/password at `/company/booking-control`. Staff identity is separate Google sign-in. Calendar, client spreadsheet and agency spreadsheet consent are separate resources; staff sign-in cannot silently grant resource access or company authority. Resource setup and paid-obligation resolution are private company operations.

The [owner recovery command](docs/company-recovery.md) handles a lost company password through protected project-owned database access. It is separate from first enrolment and never exposes a public reset route.

Switching OFF immediately closes new booking admission. Public booking, receipts, name-and-phone lookup and the booking dashboard are denied. General website content and enquiries remain independent. Staff can read enquiries at `/enquiries-studio`. Existing paid obligations are preserved for private company resolution; OFF itself neither cancels nor refunds. An older ON acknowledgement cannot defeat a newer OFF or a restored authority generation.

## Database and background work

A contained installation has one canonical schema in its own database. Routine web, staff, worker, company, read-only backup and maintenance roles are separate. Runtime logins cannot write raw tables or own the schema. Constraints protect capacity; external provider requests do not hold SQL transactions. Saved operation identities, leases, versions and credentials are rechecked at completion.

Nine common lanes are the only asynchronous consumer entry. The worker's timer ticks every 15 minutes but reads its own notebook first (the "quiet timer"): it wakes the website and its database only when saved work is due, or one hint for work due before the next tick, after a wake ring, for a retry or a back-off re-check of stuck work, and for a safety check every 12 hours. Worker health is green only when the timer ticked within 20 minutes, the last full check is at most 12 hours 20 minutes old and found nothing failing or stuck, and no wake ring is waiting. After a Google set-up step or an operator tool that creates background work without ringing, expect a wait of up to 12 hours, or open the company controls page, which rings on every status read.

Sleep mode while booking is OFF: each tick also reads the worker's own signed ON/OFF copy through the internal path `/internal/recovery-state` of the product-state object (never Neon; not reachable from the internet). After OFF is published, one full "drain" run that starts at least 150 seconds later finishes what is owed. While the copy is OFF and settled, that run or a later one found nothing failing, stuck, re-checking or remaining, and no wake ring waits, the site rests: the 12-hour safety check is replaced by one check every 7 days, while known due work still runs on time and every wake ring still runs at once. An unreadable, pending or ON copy keeps the 12-hour pace. While resting, health allows a full check up to 7 days 20 minutes old (until the next completed run), so a broken website-to-database path can stay unnoticed for up to a week on a site without a daily backup, and work whose wake ring was lost at network level (both website tries failed) can wait up to the next weekly check, for example a practice notice of a new enquiry. Every accepted switch change, every company status read and every records re-check rings the worker; a status read also republishes a change still on its way, and the page re-checks by itself every 20 seconds for up to 10 minutes. `/wake` answers 503 unless its durable wake note was saved, so the website's second try fires. The observer runs eight minutes after each quarter hour and never reads the database. Independent public-repository monitoring and backup workflows have strict guards before allocating a runner. They contain no deployment or test-before-every-publication job.

## Copying and proving a release

`tools/install/package.py` builds/verifies a deterministic manifest, requires the exact target Git root and declared project identity, stages an entire copy, preserves unrelated files/settings, and supports exact interrupted-installation recovery. It refuses package links, extra files, tampering and an unrecognized existing copy. The source and every installed copy must have the same content digest.

The acceptance suite uses synthetic data, native isolated PostgreSQL 16/18, native Cloudflare storage and Chrome. Real provider acceptance, public deployment, migration of historical records and sustained monitoring are separate evidence. A passing unit suite or a coverage figure cannot substitute for those checks. No archive, key, customer record or credential is stored in GitHub artifacts.

The contained [historical handover commands](docs/handover-commands.md) provide read-only preview/difference checks, prepare, journal readiness, final fenced conversion, checked completion and checkpoint inspection after an interrupted response. Their reviewed selections contain reader names only; the normal protected runtime settings supply credentials. Database layout recognition includes exact trigger definitions and enabled states. The inspected Sarsa publication with four comment-only function differences has its own exact accepted fingerprint; unrelated function changes remain refused.

## Website display bindings

`contracts/surfaces.json` is the shared application/host route policy. `hosting/routing.mjs` selects generated page variants and guards exclusive booking assets using the installation-bound signed worker projection. It never opens the database or sends customer headers/query values to the projection service. The host wrapper supplies its platform's `next` and `rewrite` functions and its own project/build manifests.

`tools/build/surfaces.mjs` traces the actual emitted dependency graph and checks the complete copied-public-file inventory. `tools/build/page-modes.mjs` creates ordinary ON/OFF metadata and sitemap variants, ON booking shells and absent raw booking defaults. Booking and receipt compatibility redirects are not permitted OFF. Project content supplies reviewed fallback wording; the package does not choose client facts or restyle pages.

`browser/product-state.mjs` and `browser/react-bindings.mjs` provide one display controller for the website. The optional module `browser/visibility.js` binds ordinary DOM attributes to that same store. `browser/conditional-work.mjs` loads optional booking-only browser work only while ON. These display bindings do not replace the server's authorization, admission or capacity checks.

`tools/checks/website-display.mjs --isolated-display-proof PROJECT_ROOT SITE_ROOT` serves built files on loopback using synthetic signed display state. It rejects form submissions and offers no application/database/provider connection. `tests/website-display-native.test.mjs` checks those files in Chrome with external requests blocked. This is display acceptance, not evidence of a connected live checkout.
