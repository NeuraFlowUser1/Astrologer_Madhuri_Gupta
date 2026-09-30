> Current execution authority: [revision5 implementation plan](permanent-system-execution-plan.md),28 September2026. Earlier dated source inventories and B-stage sequences below are historical; revision5 and the resource manifest distinguish current implementation from pending hosted proof.

# Source audit and evidence register
21 September2026. Static read-only inspection of selected source and current plan checkpoints. Not a live incident investigation: no production logs/private records/accounts were read. Owner confirmed “outreach” means this website’s booking and notification flow. Prior visual feedback is recorded in client design history; earlier006/009/014 animation fixes remain design requirements, not newly claimed backend defects.

Paths below relative to repository root. Critical means must address before real paid bookings, not a claim that an exploit/incident occurred.

| ID / priority | Evidence | Consequence | Planned resolution |
| --- | --- | --- | --- |
| S01 critical |004 frontend/src/pages/Booking.jsx:116–125; backend/main.py:926–973 | API/provider error invents available default slots | Error/empty distinction; database policy/claims; no fake fallback |
| S02 critical |004 backend/main.py:1181–1263 | Immediate confirmed response, no payment or slot transaction in this path | Replace with hold/order/verified-paid finalizer; retire both aliases1267–1274 |
| S03 critical |004 backend/main.py:1228–1249 and1307–1323 | Daemon thread may vanish after success; no durable enquiry save before acknowledgement | Transactional booking/enquiry records and durable delivery jobs |
| S04 high |004 frontend/src/pages/Booking.jsx:111–127,188–192 | Old date response can overwrite newer; date change does not clear selected slot here | Abort/generation guard, date-bound selection, revalidate at checkout |
| S05 high |004 backend/main.py:935–962,1015–1016; parse_time_string421–430 | UTC-labelled naive local times and stripped offsets; invalid time defaults10:00 | Explicit practice timezone, strict date/time validation, server clock |
| S06 critical |004 backend/main.py:967–968 and creation path | Availability permits one overlapping event; create does not enforce capacity | Single-practitioner capacity1 transaction; approved capacity policy only |
| S07 high |004 models325–336, phone validator372–377 vs frontend159 | Phone required by UI but omitted/empty/non-digit can become None string server-side | Mandatory normalized email/mobile on every mutation contract |
| S08 high |004 frontend61–65,209–230; backend325–336 | Hardcoded price display; no payment/quote verification in inspected endpoint | Server catalogue/versioned quote and provider amount validation |
| S09 high |004 backend1201–1207; Contact1292–1297 | Cached email token existence accepted without matching submitted token; global bypass flag spans flows | No global bypass; new booking-only no-OTP model; preserve separate Contact authentication |
| S10 high |004 backend454–482,1066–1067,1096–1097 | Provider acceptance labelled delivered; false return ignored; timeout→SMTP may duplicate | Persist delivery state, provider events and stable retry keys, no blind provider switching |
| S11 high |004 backend77–306 | Redis errors silently divert counters/cache to local SQLite; read/modify counter can race; failure returns1 | Shared authoritative admission state; explicit outage; atomic committed limits |
| S12 medium |004 backend1005,1014,1033,1110,476; CORS43–48 | Personal details in logs/event bodies; broad credentialed origins | Minimal redacted logs/messages, least-privilege same-origin API and policy review |
| R01 adaptation-critical |003 src/backend/models.py:32–34,53–83; application372–379; storage245–249 | Checkout tied to OTP; email hold uniqueness assumes verified identity | Sarsa-only contract/admission rewrite, not deletion of the modal |
| R02 retained strength |003 storage219–270,272–309; payment_checkout149–215 | Atomic ownership/quote/payment disposition supports safe reuse | Retain invariants; extend no-OTP concurrency/security tests |
| R03 improvement |003 booking_delivery.py:165–173 | Customer AND studio booking mails wait for ready Meet URL | Separate immediate paid acknowledgement/attention from meeting details |
| R04 retained strength |003 delivery claim143–190, run296–318 | Durable leased/versioned jobs and stable send keys | Keep; verify late retry/idempotency-window and stale-message behaviour in Sarsa |
| R05 retained strength |003 useBookingSchedule.js:1–65 | Rejects invalid availability and stale effect responses | Reuse behaviour; preserve explicit selected-date/slot reset contracts |
| P01 current design gap |004 design-review/2026-09-17/12-booking-experience/design-spec.md | Accepted visual demo still request-based, contact email OR phone | New automatic HTML must require both, show fees/real-slot semantics, no OTP |
| P02 downstream wording |00414 Contact and13 reference describe email verification in booking | Would contradict latest booking decision | Latest shared plan overrides history; update cross-page Booking copy during B2 |

## Recorded prior fixes, not current unfixed incidents
003 Plan1 Resume here records an expired-unpaid receipt correction: automatically clear only definitively unpaid expiry, preserve uncertain/paid/manual-review cases. Its September15 checkpoint also records production backup/restore and earlier delivery/hosting evidence. These are dated evidence, not today's health check or fresh proof for Sarsa. The inspected tests include test_only_one_active_hold_per_email, wrong-receipt/signature rejection, quote-change and receipt-expiry contracts. Adapt OTP-dependent assertions; do not keep the old email uniqueness invariant unreviewed.

Sarsa design history records final→unformed→formed flashes, hero waiting for scroll, slow section timing and duplicate FAQ disclosure states. Preserve pre-paint initialization, load-start hero, entry-triggered one-shot sequences, immediate focus settlement and synchronous FAQ exclusivity. No whole-site fresh visual audit performed in this booking planning turn; current planning board is inspected separately.

## Official provider references consulted
- Razorpay standard checkout build guide: https://d6xcmfyh68wv8.cloudfront.net/docs/payments/payment-gateway/web-integration/standard/build-integration/ (official documentation mirror; indexed content is older; current direct markdown endpoint could not be rendered by browsing tool).
- Razorpay webhook validation: https://razorpay.com/docswebhooks/validate-test/?preferred-country=SG (official indexed page explains signed raw-body validation, duplicate event IDs and non-guaranteed event ordering).
- Razorpay payment OTP: https://razorpay.com/rupay-otp/ (bank/card authentication is distinct from this site's email OTP).
- Resend idempotency: https://resend.com/docs/dashboard/emails/idempotency-keys (24h retention; must not assume indefinite duplicate protection).
- Resend event types: https://resend.com/docs/webhooks/event-types (delivery outcome events; provider acceptance is separate).
No account feature/cost/live health assertions. Official provider configuration must be rechecked during authorized integration. No third-party commentary used as technical evidence.

## Planning verification boundary
Source audit only. No backend imports, executable integration tests, messages or financial actions. New HTML is a read-only planning viewer, not a checkout. Local plan-viewer syntax/links and screenshots checked separately. Required production build attempted; exact result in verification.md.


Revision2: read [tightening-review.md](tightening-review.md) for additional evidence and [implementation-contracts.md](implementation-contracts.md) for precise fixes. The old reference not_received state is not authoritative proof of terminal unpaid; C04 overrides any implication to the contrary.

## Revision3 source recheck —22 September2026
Rechecked004 App.jsx/HashRouter/Render warm-up and vercel.json SPA-only rewrite;003 vercel.json API-before-SPA, application.py booking readiness, storage.py payment projection/exception enqueue, payment_checkout.py reconciliation bounds and migration005 unique index. Earlier cited risks remain present in inspected source. Provider resources, customer records and current production deployment were not accessed; repository evidence is not live-account inventory. See permanent-system-execution-plan.md for the current sequence and open resource manifest.

Revision4 trace:003 storage.expire_holds releases capacity independently from financial resolution; storage.hold serializes schedule and checks verified-email active holds; payment_checkout._pinned uses literal current key_id/mode; PaymentEvents.receive persists signed account-checked event/hash plus processing intent before acknowledgement. This motivated context ownership/lock-order and credential-rotation design detail while retaining the existing durable inbox. External-calendar independence is an architecture constraint, not a newly observed incident.
