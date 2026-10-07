# Contained appointment and enquiry system

This package is the neutral master for independently owned project copies. Identity, business policy, accounts, website content and protected values belong to the installing project. The package cannot select another project or load a factory runtime.

## Current implementation status

The common foundation includes the approved booking-experience refinements: draft retention through tab checks, V3 optional email, accessible date/time controls, shared receipt facts/PDF/requested email copy, and thin receiving-site adapters. The [implementation contract](docs/booking-experience.md) explains the data, dependencies, migration and controlled cutover. Source-bound test, qualification and per-installation production observations are recorded in the programme evidence and checkpoint; an older release's evidence does not automatically qualify a new digest.

## Project folder contract

Keep `appointment-system/` and `appointment-settings/` as siblings inside the actual project repository. The settings folder contains `project.json` and `business-settings.json`; protected values are supplied only through that project's own account/environment. The serving entry verifies `release.json` once before importing provider composition, binds only its sibling settings and requires a fresh process for identity changes.

`project.json` declares installation, project, environment, official origin/aliases, independent database targets, approved owners, sender, providers, worker and the classified website surfaces. Basic commercial settings are separate from protected connections and internal retry parameters. The migration target is a declared direct owner connection, separate from the six routine purpose connections.

## Authority and the service switch

The company enters through username/password at `/company/booking-control`. Staff identity is separate Google sign-in. Calendar, client spreadsheet and agency spreadsheet consent are separate resources; staff sign-in cannot silently grant resource access or company authority. Resource setup and paid-obligation resolution are private company operations.

The [owner recovery command](docs/company-recovery.md) handles a lost company password through protected project-owned database access. It is separate from first enrolment and never exposes a public reset route.

Switching OFF immediately closes new booking admission. Public booking, receipts, support/recovery and the booking dashboard are denied. General website content and enquiries remain independent. Staff can read enquiries at `/enquiries-studio`. Existing paid obligations are preserved for private company resolution; OFF itself neither cancels nor refunds. An older ON acknowledgement cannot defeat a newer OFF or a restored authority generation.

## Database and background work

A contained installation has one canonical schema in its own database. Routine web, staff, worker, company, read-only backup and maintenance roles are separate. Runtime logins cannot write raw tables or own the schema. Constraints protect capacity; external provider requests do not hold SQL transactions. Saved operation identities, leases, versions and credentials are rechecked at completion.

Nine common lanes are the only asynchronous consumer entry. Scheduled recovery runs every 15 minutes; the observer runs eight minutes afterward and never reads the database. Independent public-repository monitoring and backup workflows have strict guards before allocating a runner. They contain no deployment or test-before-every-publication job.

## Copying and proving a release

`tools/install/package.py` builds/verifies a deterministic manifest, requires the exact target Git root and declared project identity, stages an entire copy, preserves unrelated files/settings, and supports exact interrupted-installation recovery. It refuses package links, extra files, tampering and an unrecognized existing copy. The source and every installed copy must have the same content digest.

The acceptance suite uses synthetic data, native isolated PostgreSQL 16/18, native Cloudflare storage and Chrome. Real provider acceptance, public deployment, migration of historical records and sustained monitoring are separate evidence. A passing unit suite or a coverage figure cannot substitute for those checks. No archive, key, customer record or credential is stored in GitHub artifacts.

The contained [historical handover commands](docs/handover-commands.md) provide read-only preview/difference checks, prepare, journal readiness, final fenced conversion, checked completion and checkpoint inspection after an interrupted response. Their reviewed selections contain reader names only; the normal protected runtime settings supply credentials. Database layout recognition includes exact trigger definitions and enabled states. The inspected Sarsa publication with four comment-only function differences has its own exact accepted fingerprint; unrelated function changes remain refused.

## Website display bindings

`contracts/surfaces.json` is the shared application/host route policy. `hosting/routing.mjs` selects generated page variants and guards exclusive booking assets using the installation-bound signed worker projection. It never opens the database or sends customer headers/query values to the projection service. The host wrapper supplies its platform's `next` and `rewrite` functions and its own project/build manifests.

`tools/build/surfaces.mjs` traces the actual emitted dependency graph and checks the complete copied-public-file inventory. `tools/build/page-modes.mjs` creates ordinary ON/OFF metadata and sitemap variants, ON booking shells and absent raw booking defaults. Booking and receipt compatibility redirects are not permitted OFF. Project content supplies reviewed fallback wording; the package does not choose client facts or restyle pages.

`browser/product-state.mjs` and `browser/react-bindings.mjs` provide one display controller for the website. The optional module `browser/visibility.js` binds ordinary DOM attributes to that same store. `browser/conditional-work.mjs` loads optional booking-only browser work only while ON. These display bindings do not replace the server's authorization, admission or capacity checks.

`tools/checks/website-display.mjs --isolated-display-proof PROJECT_ROOT SITE_ROOT` serves built files on loopback using synthetic signed display state. It rejects form submissions and offers no application/database/provider connection. `tests/website-display-native.test.mjs` checks those files in Chrome with external requests blocked. This is display acceptance, not evidence of a connected live checkout.
