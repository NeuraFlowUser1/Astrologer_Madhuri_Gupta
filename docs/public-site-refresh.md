# Sarsa: preserve and refine the restored website

Current objective: the owner accepted the moving preserve-and-refine candidate on 10 October 2026 and authorized its commit/push through the existing publication route, explicitly skipping test suites. The approved presentation augments the restored website in .local-runtime/version-a-restore, based on commit 39aaedf34eb046b3bae106ea579bb8c0b375fcc0. See the [publication scope](public-site-refinement-release-2026-10-10.md).

The enclosing dirty client checkout and rejected public-site-refresh workspace remain separate and are not source donors. A Git push, the hosting provider's deployment result and a current public-page observation are separate facts; record each against its exact commit rather than reuse the restoration's dated receipts.

## Current public website

The original Georgia/system typography, forest/cream palette, still-life photograph, authentic portrait, section order and 36 staged scenes remain. Home has a taller proportional hero and readable copy, simple English with short Hindi lines, restrained optional margin artwork, service-card glow, eight exclusive FAQs and a Home back-to-top button. About adds the approach action, clearer service action and separate Explore/Book controls for all four services. Services keeps its existing two-column directory and adds four illustration bands, a question guide and a short Jyotish glossary. The four service pages retain their original animated artwork.

Contact keeps all five original scenes. Its shorter rear-card wording fits the uncovered area; the original front-card wording remains to preserve its natural size at every narrow width. The existing closing arrow is now a real 44px booking link. A readable booking explanation and location block sit outside the original scenes. The address is exactly **8, Gailana Road, LIC Colony, Agra - 282007** and the external pin is https://maps.app.goo.gl/CwQftW8iYfxAZFDo8. The real Google embed was visually checked locally. Its text address and directions link remain usable when the frame is blocked.

One persistent public header/footer serves the public pages, including Booking, Contact, help and policies. The header stays sticky only on Booking. Its connected reference is passed to the unchanged booking-layout helper. Public anchors have one interruptible 400ms scroll owner with instant reduced-motion behavior and outside-scene keyboard focus markers. Contact topic scrolling and Booking's original 220ms stage scrolling remain separately owned.

## Motion boundaries

Exactly two geometry exceptions were agreed: Home hero height/proportional crop/height-dependent curtains and removal of its unused outer reserve; and About service-row spacing for the two actions below 1200px. The original timing and movement formulas remain. About's original page-root background shapes receive a measured compensation for the added row height, preserving their original bounds. The only edit to an existing motion module is About's selector adapter from whole-row buttons to permanent row identity elements.

Home's emblem and process remain separate original canvases. Their requested repositioning/merger is excluded under the owner's position lock. Contact's original FAQ number/line alignment is likewise retained. Do not describe those earlier geometric requests as completed.

The common scene engine, Home/generic/Kundli/Contact motion modules, Booking layout helper, Contact form/hook and service catalogue match the preserved baseline byte for byte. Disabled About ambient styles remain disabled. No Pause background movement button is present.

## Protected product contracts

All 633 inventoried appointment-system/settings files are unchanged: 573 contained release files and 60 settings files. No API payload, database, migration, provider, price, duration, authentication, stored booking, permission, private portal, dependency or lockfile changed. Existing service IDs, product-state bindings and latest-at-click admission guards remain authoritative.

Booking email follows the current form: optional when email-code checking is off, required and verified when it is on; mobile remains required. Contact enquiries use their separate email verification. Home FAQ, Contact answer, Privacy and Terms now describe this correctly. Payment confirmation, receipt status and Meet/email delivery remain distinct. Existing help/recovery routes remain.

## Focused local verification

The 9 October local implementation evidence is retained in the client-scoped folder design-review/2026-10-09-preserve-and-refine/implementation, outside this application Git root. The evidence is local Chromium and synthetic contract proof, not a hosted release or physical-device certification. The owner reviewed and accepted the actual moving candidate on 10 October. No test suite is rerun for this push, at the owner's instruction.

- 138 focused tests in 9 files pass. All 19 changed application/build executable files exceed 90% statements, branches, functions and lines individually, with no exclusions. Aggregate results: 98.82% statements, 96.66% branches, 98.61% functions and 99.73% lines. This is not coverage of every untouched website/shared-system file.
- The browser checks cover shared public navigation, the action destinations, FAQs, Top, anchors, form retention, both booking email modes, unavailable/unknown booking, image/map failure and 200% zoom-equivalent layout.
- Original/candidate motion comparisons cover 36 scenes, 8 viewports and 18 sampled progress points. Protected object geometry/styles match outside the two recorded exceptions. About root backdrops are compared in their actual root coordinate system; row identities are compared within each row.
- Eight native-clock observations cover Contact's 24s and 36s full return cycles in both builds at phone and desktop widths, with offscreen, simulated-hidden and reduced-motion checks. Home attention runs with one light at a time, no consecutive repeat, manual focus priority and reduced-motion cancellation.
- Production compilation and the 12-route public boundary preflight pass. Lint has zero errors and four pre-existing warnings in unchanged tests.

For a later expressly authorized verification run, the focused checks are reproducible from this source root. Do not run them as part of the 10 October push:

    npm --prefix frontend run build
    npm --prefix frontend run lint
    npm --prefix frontend run check:public-site
    cd frontend
    npx vitest run --config vitest.refinement.config.mjs --coverage

The client-scoped implementation folder contains the separate focused browser runners. They serve/visit the actual compiled app with synthetic contracts and block real application/provider requests. The separately observed public Google map is read-only. No checkout, enquiry, email or payment is sent to a real provider.

## Review, release and recovery

The owner completed visual review and authorized publishing this accepted version through NeuraFlowUser1/Astrologer_Madhuri_Gupta, main, and the existing connected Vercel project/official Sarsa domain. Full local/hosted suites are skipped. No manual GitHub Action, shared settings/data/provider change or customer action is authorized by this presentation push.

The owner's next requested work is planning: richer generated service imagery, combining the Home emblem/process while retaining their multi-stage motion, stronger hover/action styling, Services spacing, and additive visual storytelling on the individual service pages. That new scope is separate from this accepted publication. Its proposed geometry/motion changes are not implemented in this commit.

Original source, tests, built output and documentation are preserved in the client implementation/before folder. Rollback is the reviewed presentation patch against the restored baseline; preserve unrelated outer work and all stored bookings. Do not reset either checkout or restore rejected redesign files.
