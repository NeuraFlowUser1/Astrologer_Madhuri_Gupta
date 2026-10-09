# Sarsa: checkpoint A restoration

Current approved objective: restore the public website from checkpoint A, `fef4f4e48eb87fe748c9d05b3be3ce4f27f6a548` (8 October 2026, 21:28:36 India time), while retaining working booking protections. The owner chose A explicitly on 9 October. The later published public redesign and unpublished M4 design are superseded. Their evidence is historical, not the current appearance contract.

## What returns

Home, About, Consultations, all four existing service routes, Contact and compact Booking return to A's actual source composition, text, images, typography, CSS, choreography and responsive rules. Three policy routes also return to A. The `/services` address stays the same but its visible label is again Consultations. A has seven Home sections with three Home FAQs, a separate process section, the original still-life hero and owner portraits. Contact restores the older layered cards, five motion scenes, four questions and enquiry desk. There is no Google map or owner address on A's Contact page. Header/footer differences between ordinary pages, Contact and Booking are restored rather than silently redesigned. Three simpler service-detail routes and the richer Kundli Prediction route return as they were. No new artwork, Hindi copy, richer service articles, M4 guide decorations, shared-menu system or back-to-top control is retained.

## Complete product exceptions from A

1. `src/booking/booking-layout.mjs`: retain the later connected-header measurement, interruption handling, optional-browser-feature guards, disposal and stale-callback protection. Remove only the rejected M4 SVG guide renderer. Movement is bounded to 220ms with instant reduced-motion fallback. These are Sarsa presentation protections, not booking-engine changes.
2. `src/pages/Booking.jsx`: pass A's own connected `.site-header` to that adapter. The form markup and wording match A; no replacement header or M4 artwork is included.
3. `src/contact/ContactForm.jsx`: consume each topic request once and apply it only to an editable, non-busy, non-blocked, non-retrying draft. Do not replay it after verification/restart. Focus a received result without forcing a scroll. Keep the original shared enquiry owner and exact submitted contract.
4. `src/pages/ContactPage.jsx`: remove A's Pause background movement button, honoring the owner's explicit standing decision. Automatic operating-system reduced motion remains. All other page markup matches A.
5. `scripts/public-pages.mjs`: retain removal of an existing generated booking-mode marker before regeneration. Repeating the build cannot leave conflicting ON/OFF markers. This does not change A's appearance.
6. Eight already-unreferenced pre-standardization component files stay retired. They were not active routes in A and are not needed to restore it. `/testimonials` still redirects to About, exactly as A's router did.

All other selected active product files match A byte for byte: 90 of 94, with four intentional source exceptions above. The build-script exception is outside that appearance-file denominator. Exact path inventories and hashes are retained in the factory restoration record.

## Preserved system

The complete contained booking package remains digest `97ab5d49fc559eb1acdeb7157d4561134d1bad824cca298506f48b2a9d32b49d`: 573 manifest files, 36 migrations. Master and contained Project003 are checked against this same release; Project003's published manifest identifies it too. The restoration changes no engine, API, SQL/RLS, database, provider connection, account permission, worker, backup job, root runtime configuration, lockfile, price or stored record. Private portals and their internal links are preserved. AstroAdvice is not visually reverted.

Optional email when email codes are OFF, required/verified email when ON, required phone, tab-change draft retention, payment/receipt/Meet status, requested email copy, PDF and booking recovery remain in the contained shared system. Enquiries have their separate required-email verification. Deliberate refresh retention is not promised. Booking stays ON; no new live payment, message, enquiry or settings change is required by this restoration. Earlier dated provider acceptance remains in `appointment-system-release.md` and is not relabelled as today's test.

## Focused verification

Run with Node22 and the committed lockfile:

```sh
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run check:public-site
npm --prefix frontend run test:restore
SARSA_EVIDENCE_DIR=/tmp/sarsa-version-a-browser npm --prefix frontend run test:public-site:browser
```

The separate test:restore command owns this bounded restoration. The existing whole-source test:public-site coverage configuration and its audit remain unchanged and are not claimed as a newly passed complete suite. It covers restored page rendering, real build/proxy entrypoints, booking/receipt/bootstrap integration, booking/enquiry/callback coordination and the two retained functional owners. Coverage is explicitly scoped to `booking-layout.mjs` and `ContactForm.jsx`, with at least90% statements/branches/functions/lines **per file**, no exclusions. This must never be described as 90% of the whole website or a full shared-system release gate. Retired design-only tests and the old redesign performance helper are archived with their retired owners. The full coverage thresholds and source inventory are preserved; the focused command does not replace or weaken them. Dependency versions and lockfiles are unchanged.

The browser command serves the actual compiled app on loopback with visibly labelled test data. Synthetic responses are checked against production contracts; no provider SDK, credentials, real mail, payment or real-customer writes are used. Only external font GETs from Google's font hosts may load; application/provider requests are blocked. It checks all12 public routes at390/1440px, Booking at eight widths320–2560px, OFF/unknown fail-closed states, four booking journeys across both email-code modes, two enquiry journeys and four lower Home motion timelines. Screenshot and code inspection supplements automated checks. Browser claims are Chromium software observations, not physical-device or screen-reader certification. Current operation checks do not claim a new full accessibility audit, performance benchmark or backend release gate.

## Release and rollback

Publish the qualified restoration commit through the existing `NeuraFlowUser1/Astrologer_Madhuri_Gupta` main→Vercel integration. Verify the official domain's actual asset hashes against the built candidate and inspect read-only health/service state/public pages. Vercel stays disconnected from Codex; do not create another hosting project or repeatedly push empty commits. Missing deployment evidence triggers investigation of Git status and public output.

The rejected M4 working copy and its exact 78-path archive remain preserved outside published source. Work occurs in `.local-runtime/version-a-restore`; `.local-runtime/public-site-refresh` is the rejected preserved workspace, not the current editing target. Roll back with a reviewed ordinary reverse commit preserving intervening work; never force/reset main. No database/provider/key rollback is necessary.

Current source and publication receipts live under the factory client's `design-review/2026-10-08-public-site-feedback/revert-identification-2026-10-09/`. They include the selected checkpoint, all file differences, focused diagnostics, screenshots, common-system comparison and actual hosted readback. Future enhancement requests are separate from this restoration; chronological staff-note history remains deferred.
