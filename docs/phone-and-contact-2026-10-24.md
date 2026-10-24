# Public phone and Contact refinement — 24 October 2026

The owner confirmed **88815-73437** for public use. The website displays **+91 88815 73437** consistently, with the native destination `tel:+918881573437`. The owner explicitly chose to retain existing scroll behaviour: only Booking keeps its header sticky; the shared footer remains at page bottom. No fixed contact strip is added.

## Customer experience

Every shared public header/footer exposes the same call link. Contact offers a call beside its enquiry-form email alternative and alongside the location/Maps action. Booking adds a short “Questions before booking?” call row in its introduction, outside disabled form fields. Other pages receive the shared contact action without repeated numbers in their content sections. Organization metadata carries the same confirmed number.

The Contact FAQ keeps its gold spine and all reveal/rotation/expand motion. Each numbered marker now has a separate grid column centred on the spine, with 18px clearance before panels on desktop and 14px on phones. The writing-stage verification note has 12px clear space above its button. Recursive visual review also found and corrected the code-entry input/button gap to 14px. No content, artwork, transition or scene controller was removed.

## Source and boundaries

`site/practice-contact.mjs` owns the number/format/destination. `PhoneLink.jsx` supplies consistent icon, text and accessible label without a custom click handler. `SiteFrame.jsx` owns shared placement; ContactPage/ContactForm and Booking own their contextual help. The existing header/booking geometry observers continue to measure actual responsive dimensions. A 320px tap-area overlap found in review was corrected by giving the header number its own full-width row at that size.

Only public presentation and metadata changed. Booking admission, fields/validation, fees, policy, forms/email verification, receipts/payments, all scene clocks/artwork, reduced motion, provider resources, stored data/settings, sealed package and migrations are unchanged. No WhatsApp availability is asserted. No real call, email, booking, enquiry or payment is submitted in verification.

## Focused proof

- 73 tests pass in seven focused files. Seven changed executable owners all exceed 90% in statements, branches, functions and lines, with no exclusions. Combined: 98.61% statements/lines, 97.82% branches and 96.84% functions.
- Targeted lint and production compilation pass; twelve ordinary public pages are generated in both existing display modes. The existing large PDF/font chunk advisory is unchanged. Whole local/hosted application suites were not rerun.
- Actual compiled Contact/Booking checked at 320, 390, 768, 1440 and 1920px: no horizontal overflow, four navigation links, correct shared/contextual phone destinations and actual observed booking header height. FAQ marker/spine centres match exactly, panel gaps remain 14/18px and the writing note/button gap is 12px.
- Default, open FAQ, keyboard focus/hover, synthetic email-code/error states, normal entry/ambient motion and reduced motion are reviewed. Isolated review uses the existing test-only server and synthetic contracts, with no provider proxy. Source motion controllers remain unchanged.

The enclosing client folder's `design-review/2026-10-24-phone-and-contact-refinement/` owns source snapshots, screenshots and detailed local/live receipts. Poster rounds 04/05 are separate untouched image-tool outputs and are not website assets or deployment proof.

## Release and recovery

Use the existing owner-approved normal Git main → Git-linked website publication path; keep Vercel disconnected from Codex. Publication and actual official-site readback are recorded separately after local qualification. Recovery is a bounded presentation revert without database migration, saved-setting restoration or booking-package rollback. Preserve old worktrees and every poster round.
