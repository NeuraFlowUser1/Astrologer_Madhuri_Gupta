# Sarsa automatic booking — reviewed implementation plan

27 September execution update: [permanent resource manifest](permanent-resource-manifest.md) records confirmed accounts and manual Vercel handoff. Supersedes earlier unknown hosting identity and planning-only authorization wording; current evidence is in the manifest; Vercel settings are screenshot-verified and Neon development access is working.
28 September 2026 · Revision5 execution plan is current. The manifest records migrations001–019 on both database branches; local payment/Google/email foundation exists, but public/frontend integration and hosted verification remain pending.

Implementation-specific strengthening: [revision4 detail review](implementation-detail-review.md).

Current execution direction: [permanent-system-execution-plan.md](permanent-system-execution-plan.md). One final system, no further mock-wiring phase; checks accompany real implementation.

Implementation details and dependency contracts: [implementation-contracts.md](implementation-contracts.md). Review changes: [tightening-review.md](tightening-review.md).

## 1. Settled instructions and scope
- Automatic available-slot booking and payment. Use project003 AstroAdvice/AstroConnect as the behavioural reference, adapted for Sarsa.
- Email AND mobile number mandatory in the UI and server contract. No email OTP in Sarsa booking. Do not substitute mobile OTP, a magic-link gate or mandatory login.
- This removes the website's email-verification step, not authentication required by a bank/payment method. Payment signatures and provider verification remain mandatory.
- No changes to003. Execution is authorized for004; development database changes are recorded in the manifest. No real customer messages/charges or production cutover from development evidence alone.
- Contact14 remains its separately approved demo with email verification/optional phone. The new instruction explicitly concerns booking; do not silently apply it to general enquiries. Booking-related copy in Contact will need alignment when the new Booking HTML is built.
- Scope is this website’s booking and notification flow. The owner explicitly withdrew the unrelated outreach-program stop/restart instruction. Reminder delivery is assessed, not promised or enabled without a defined policy.
- Outcome sought: clear interfaces and explicit invariants, recovery, monitoring and evidence. Do not promise an airtight or bug-free distributed system.

## 2. Legacy/reference wiring and current implementation
Current004 implementation: backend/booking_engine contains the development-tested reservation/payment core, HTTP application factory and saved-work recovery consumers; see verification.md and permanent-resource-manifest.md. It is not routed from the public website. Approved service prices/hours, Google Meet and website staff-calendar authority are recorded in the manifest.

### Sarsa legacy application
Booking.jsx → Render-host fallback or configured backend → /api/otp/send and /api/otp/verify → /api/available-slots → /api/book-appointment → generated Jitsi URL + immediate confirmed response → daemon thread for Google Calendar, dual Sheets and Resend/SMTP mail.
There is no captured-payment verification or authoritative durable booking/slot transaction in this inspected creation path. Redis/SQLite here is a cache, not a transactional appointment ledger. Neither the newly designed12 Booking nor14 Contact HTML invokes these endpoints; both are local demonstrations. Source configuration is not proof the production domain currently runs this exact version.

### Project003 reference
React page → server policy/quote/availability → BookingInput with required email/phone and verification token → protected receipt + schedule-locked hold → persisted payment-order intent → official Razorpay checkout → server-fetched payment finalization, also reached by signed webhook/recovery → confirmed booking and durable delivery jobs → Calendar/Meet, customer/studio mail, Sheets. Private studio tools surface exceptions. Database is authoritative; Sheets mirror it. Reference source retains OTP; this cannot be copied unchanged for Sarsa.

### Notification distinction
A booking record, captured payment, ready meeting link, email-provider acceptance and recipient-server delivery are separate facts. Delivery does not prove the person read a message. Current Sarsa Calendar reminder configuration is not proof of customer reminder delivery; no independent SMS/WhatsApp/reminder programme was verified. Mandatory phone does not authorize a new messaging channel or marketing consent.

## 3. Target journey and section-specific design
The six-section composition reviewed in12 is the starting visual reference. Replace its preferred-time request semantics completely. Do not transplant Contact's oval or weave.

Shared values: plaster#f7f5ef, paper#fffdf8, forest#26483d, deep#183d31, ink#21392f, sage#e4e9df, clay#955d45. Georgia/system. Max1220px, gutters40px desktop/20px phone; section gaps88/56px; panel24px corners, controls10–12px; shadows0 20px45px rgba(38,72,61,.16). Titles52–56/36–38px, section38–42/30–32px; body17/16px; inputs16–17px; labels14px; essential help14px; min44px hit areas, primary52px. Breakpoints950/650/380. No copy overlay on animated light.

### A. Opening / the invitation folio
Design intent: personal welcome and immediate understanding of the appointment process.44/56 copy/folio split; mobile title→280px artwork→support/actions. Keep accepted opening language, no fabricated office/credentials. Main CTA Choose a consultation, secondary Ask a question.
Assembly3800ms: covers release0–950ms; paper rotates flat650–2250ms; consultation tab rises1900–3400ms; final rule resolves3400–3800ms. Travel<=48px desktop/24px phone, rotate<=18deg. One optional14s light pass across empty background after completion. Copy/button available immediately; no delay gate.

### B. Services / the consultation index
Design intent: make service choice explicit, retain allowlisted incoming service, do not auto-pick one on generic entry.30/70 editorial introduction and four service choices from the approved catalogue. Actual fees/durations supplied by server; the approved current catalogue is recorded in revision5 and policy.py. Prototype sample numbers are not authority.
Assembly2300ms: index spine draws0–500ms; individual sheets emerge350–1400ms from staggered18–28px depths; service emblems register1250–2100ms. Selected seal appears only after a real selection. Stable radio inputs, keyboard arrows, text+check selection. On phone one column. Hover reveals an underline and turns an emblem4deg, never moves target bounds. Price unavailable means unavailable, not zero/free. Service change invalidates quote/date-slot compatibility and forces review; retain contact draft.

### C. Appointment / the observatory window
Design intent: honest availability and a comfortable date/time decision. Forest35/65 split, light appointment panel. Date strip and native date fallback, available slot buttons grouped by approved periods; explicit practice timezone. Server-provided current day/horizon avoids device timezone mistakes. No selected slot until chosen.
Assembly2600ms: frame corners approach0–650ms; inner shutter retracts450–1500ms; date rail unfolds1050–2000ms; time markers register1700–2600ms. No repetitive card fly-ins. Phone shorter travel, normal vertical flow. Loading, no slots, closed day, connection failure, stale slot and retry are distinct. Date change immediately clears selected time and old slot data; abort or ignore old responses. Background refresh may preserve last display but disables payment progression until refreshed. Availability is advisory until atomic hold, never a reservation on click.

### D. Details / the correspondence register
Design intent: accurate contact details with no verification detour.62/38 form/recap; recap above form under950px. Required name,email,mobile; consultation-specific preparation fields only when approved. Explicit country selector and normalized international phone; do not label it verified. Unknown birth time is a real option if service allows; never fill noon or force an invented value. Field policy remains a client-specific configuration item.
Assembly2100ms: paper edge opens0–600ms; horizontal writing rules align350–1200ms; recap margin hinges into position1000–2100ms. Form groups become readable, then stay still. Focus/pointer settles immediately. No per-keystroke animation or delayed controls. Validate on Continue, associate inline errors, focus first error, preserve values. Email max254, name2–100, mobile valid supported-country number, notes max4000; birth dates real and nonfuture. Review echoes full entered email/mobile with Edit links. No “verified” tick for syntax alone.

### E. Review and payment / the booking docket
Design intent: explicit informed payment action. Centred860px paper docket: service/amount, day/time/timezone, contact details, preparation summary; discreet edit links. Phone one column, full-width Pay amount action; no sticky button covering keyboard/content. No checkout countdown before a hold exists.
Assembly2200ms: summary strips align0–750ms; a vertical stitch connects rows450–1450ms; amount plaque registers1150–1800ms; payment action closes the docket1600–2200ms. Hover edge illumination; form controls fixed.
Pay action revalidates server quote/availability and contact fields, performs admission checks, creates/reuses hold and payment-order intent, then opens official checkout. Hold timer is derived from server time/deadline; default reference policy ten minutes capped at appointment start, subject to schedule configuration. No expiry reset on refresh/retry. The hosted payment UI follows provider design, not a homemade payment-card form. Decline/close is not proof no charge happened: reconcile original order first.

### F. Outcome and practical answers / the appointment receipt
Design intent: explain exactly what happened and the next safe action. Outcome replaces the review action region; preserve earlier sections/draft. Calm receipt with separate Appointment / Payment / Meeting details / Email rows; help link with non-secret booking reference. Below it a narrow editorial FAQ rather than Contact's bound leaves.
Assembly only on confirmed server outcome,<=900ms: appointment rule draws0–250ms; factual rows settle150–600ms; small confirmation seal appears550–900ms. No celebration on browser payment callback. Checking/review states use static copy and a restrained progress indicator, not a success seal. FAQ initial assembly1800ms: margins align→rules extend→answers appear. No repeated looping status claim. Reduced motion instant.

All lower sections start timed assembly once at meaningful viewport entry (top70%, bottom15%); no scroll-progress dependency, no reset on re-entry. Initial unformed CSS before paint. Auto-tour is review-only, hero+2s hold then85px/s; interaction pauses, form focus settles, reduced motion disables. UI must work before motion completes. Preview1440x1000,390x844,360x800,320px reflow; keyboard,200% zoom, short landscape, slow network and mobile keyboard during implementation.

## 4. No-OTP backend contract: deliberately replace identity assumptions
1. Sarsa BookingInput derives from validated BookingDetails plus request_id, NOT VerifiedInput. Remove booking verification_token and consume_verification from the checkout path and booking UI state. Keep Contact/other protected flows untouched. Do not set BYPASS_OTP_VERIFY globally or fabricate verified tokens/flags.
2. Required phone/email on API and UI. Reject absent/null/blank/malformed values. Normalize phone consistently with explicit country; format validation does not prove ownership, deliverability or that a line is mobile. Payment contact metadata cannot overwrite the reviewed booking contact silently.
3. Anonymous checkout context plus cryptographically random request_id/receipt secret retained before first mutation. Receipt proof authorizes resume/status, not entered email/phone. No public “find my booking by email” lookup. Store only necessary opaque recovery material in sessionStorage as reference does; no draft/birth details/tokens in URLs, analytics or logs. If storage unavailable, warn about limited refresh recovery before payment and keep current-tab receipt in memory; do not discard it. SessionStorage is not durable cross-device recovery.
4. Reference's one-active-hold-per-email rule follows verified identity. Remove that assumption in Sarsa: a supplied email must not disclose another checkout or let an attacker block someone else's address. Enforce one active hold plus the independent unresolved-checkout ownership guard from R4.1 per admitted checkout context, with global/IP/context velocity controls. Email/phone signals may inform risk internally, not authenticate or unconditionally lock out a victim.
5. Admission happens before hold/order creation. Proposed initial configurable thresholds for load testing:5 new checkout attempts/10min per context;20/10min per IP as an additional-challenge threshold, not a blanket shared-network ban; one owned unexpired hold/context plus at most one unresolved checkout/context, including after hold expiry. Trusted platform-derived client IP, not arbitrary forwarded headers. Counters committed separately from a rejected business transaction, so a rollback does not erase abuse evidence. Repeated identical authorized request resumes without new quota/hold/order. Fingerprint change with same request_id gives409. Global cost/occupancy alarms and bounded admission; optional managed bot challenge when risk warrants, never another email OTP. Product-specific bot mechanism and limits need validation under real traffic; these numbers are proposals, not proven capacity.
6. Anonymous context alone is not strong bot protection: attackers can rotate cookies/IPs. Before launch, prove admission controls under simulated abuse and agree owner capacity/cost limits. If admission store is down, reject new checkout safely; recovery of already-paid work must remain separately prioritized. Do not claim OTP removal has identical abuse exposure.
7. Show full email/mobile at review and allow correction before hold. Warn gently about obvious email-domain typos without silently rewriting. No verification status asserted. Once a checkout exists, details/price/slot frozen. To edit, reconcile the existing order and explicitly abandon only when safe; uncertain money keeps original case active. Post-payment contact correction requires authenticated studio authorization, audit and versioned delivery. The viewing receipt alone does not authorize a self-service contact change, cancellation or refund; see C03/C05.
8. Without ownership verification, a valid but wrong email can receive booking details. Keep outbound customer messages minimal: no birth data/free-text/private administration links; distinguish receipt access from email address. Meeting-link disclosure risk remains and must be visible to owner; review step/support correction mitigate, not eliminate it. No card information stored by Sarsa. Lost receipt uses verified studio support process, not public email+phone lookup.

## 5. Booking/payment invariants and state transitions
- Authoritative relational database transaction owns capacity. For current single-practitioner fixed-duration assumption, unique slot claim; if approved durations vary, add overlap-safe interval enforcement before enabling them. No Calendar overlap_count heuristic.
- Hold, canonical quote snapshot, receipt digest and payment-order intent committed together. No provider call while holding a long database lock. Crash after commit recovered using same request/order intent. Unknown order-creation result reconciled by provider receipt; do not create a second order because a response timed out.
- All entry paths—browser confirmation, signed webhook, scheduled recovery—use one idempotent finalizer. Check provider order association, merchant/mode, amount,currency,capture and refunds. Browser paid:true never confirms. Unique payment IDs and signed-event IDs; duplicate/out-of-order events cannot erase financial evidence. Refund observations remain real later facts; appointment cancellation is an explicit separate transition.
- Confirm only matching captured payment and owned unexpired hold, using server time. Late capture after expiry becomes visible payment attention; never steal a slot from another visitor. Preserve every financial observation.
- Confirmed booking and delivery intent saved in same transaction. Queue publication may fail; a recovery sweep republishes persisted work. Provider failure never changes a paid confirmed appointment to unbooked.

| Observed state | Visitor action | Server rule |
| --- | --- | --- |
| Draft/selection | Continue or edit | No hold created merely by viewing dates |
| Availability unavailable | Retry or ask for help | No invented slots, no checkout |
| Quote changed/slot lost | Review change or choose again | No automatic repricing/charge |
| Creating order/response unknown | Check original checkout | Same receipt, no duplicate hold/order |
| Hold+ready checkout | Pay/resume while deadline valid | Deadline immutable; amount from server |
| Checkout closed/declined | Check status, then retry if allowed | UI dismissal is not definitive payment failure |
| Captured+valid claim | View confirmed appointment | Single finalizer and durable notifications |
| Confirmed, meeting/email pending | Keep confirmation; check details | No second payment |
| Expired, server authorizes safe restart | Choose another time | C04 proof required; absence of a local payment row is NOT sufficient. Never auto-clear an exposed/unknown order. |
| Expired+unknown/captured/mismatch | Needs attention/status/help | No pay-again primary, no silent reset |
| Cancelled | Show actual cancellation/refund separately | Cancellation is not automatic refund |

Client polling proposed2s→5s→10s capped, respecting server Retry-After; pause hidden, reconcile on return. After60s switch to stable “still checking” with manual refresh/help, not failure. Background recovery continues. These UI timings are not payment completion promises.

## 6. Communications and operations
Use003's durable outbox, leased workers, bounded backoff, per-recipient/versioned jobs, signed delivery events and scheduled rescue. Separate paid booking acknowledgement from meeting preparation: source003 currently waits for Meet before customer/studio confirmation mail. Proposed Sarsa improvement: one promptly queued minimal paid-booking acknowledgement, then one meeting-details message when ready; staff also sees paid work immediately in dashboard. C06 specifies3mail jobs per booking (customer/studio acknowledgement + customer meeting details), new kind/recipient constraints, queue/worker routing and budget implications. Acknowledgement is queued promptly, not guaranteed immediately delivered. No duplicate Calendar auto-invitations.

Never label Resend API acceptance “delivered.” Persist provider message ID and process signed delivered/bounced/failed events with event dedupe. Keep outcome priority so older events do not erase a bounce. Unknown sends retry with the same provider key/payload within its documented window; after24h unknown acceptance requires reconciliation/attention, not blind send or SMTP fallback. Permanent failure surfaces to studio; do not send infinitely to a bounced address. Calendar/Meet creation uses deterministic event IDs and versioned update/cancel handling. Sheets are secondary, keyed mirrors; no mirrored-sheet outage may block confirmation or determine availability.

Before launch verify: private studio authentication, closures cannot overwrite holds/appointments, cancellation vs refund distinction, any retained reschedule workflow atomically swaps claims and versions delivery, pending stale jobs are suppressed and unavoidable in-flight delivery races receive versioned correction, pending paid work visible, independent alerts if email itself fails, backup/restore proof and least-privilege client separation. No promotion messages, SMS/WhatsApp, discount capture, or new reminder campaign in this scope.

Proposed internal alerts for review (not customer SLA): paid delivery pending>5min; missing meeting within60min of appointment; unresolved payment/order>2min; retry exhaustion/bounce/revoked Calendar immediately; backup age>26h. Tune to approved monitoring cadence and hours; identify actual responding owner before go-live. Track age/outcome, not raw contact/birth information. Duplicate confirmed slot count must remain0. Any proposed reliability percentage awaits measured baseline and realistic incident coverage.

## 7. Implementation sequence and completion evidence
B1 (completed history) — This reviewed plan + source audit + visual planning board. Owner review before complete revised HTML.
B2 (completed history) — Revised Booking HTML in new client review folder, retaining12 as history. All main and exception states; synthetic labelled fees/slots; no provider calls. Update Booking CTAs in Contact/Home/Kundli/About and booking-related FAQ wording to new no-OTP flow. Acceptance: desktop/mobile screenshots, stable form, selection/edit/validation/no OTP, all UI exceptions demonstrable locally. Synthetic HTML does not prove access controls or payment correctness; those require final-system database and provider evidence under revision3.
E1–E6 — Continue directly into the permanent system using [revision3 execution checklist](permanent-system-execution-plan.md). Establish the actual application/resource manifest; implement authoritative booking/admission and final payment adapters; wire calendar/email/queue/recovery; integrate the reviewed React route; prove the same system under controlled access before opening public intake. These are dependencies in one implementation, not isolated mock/production builds. B3/B4/B5 references in dated history are superseded as sequencing, not as removal of their correctness checks. A later small real payment is explicitly agreed at that time; no fixed amount or charge is authorized by this plan.

## 8. Verification matrix required before real acceptance
| Test | Expected proof |
| --- | --- |
| Missing/null/blank email or mobile; malformed/international numbers | UI + API reject consistently; no mutation/order |
| Booking without OTP/token | Valid admitted request works; zero email-OTP calls; Contact protection unchanged |
| Spoofed email of another held booking | No information leak; cannot hijack status or exclusively block that email |
| Context/IP bursts + unavailable limiter + shared IP | Bounded new holds/cost; legitimate flow path; existing paid recovery unaffected |
| Two browsers race for same slot | Exactly1 claim; loser409; no double confirmation |
| Replayed same request, changed payload, wrong/revoked/missing receipt | Same result; changed request409; unauthorized no private data. Valid stolen bearer receipt is a residual credential risk, not magically rejected. |
| Date-change stale response; device timezone/year mismatch; closed/past date | Correct server-policy day/slots, old selection cleared, no fake fallback |
| Quote changes, unapproved service/duration | Explicit fresh review; server total only |
| Lost order response/process crash | Recover original order; no second order on unknown result |
| Fake browser success, wrong signature/merchant/order/amount/currency/refund | Never confirm, preserve attention where money exists |
| Duplicate/reordered webhook + browser callback race | One financial disposition, one confirmation, deduped jobs |
| Capture after expiry and another owns slot | Financial case retained, new owner unaffected |
| Close checkout, refresh, missing storage, expired unpaid vs unknown | Correct protected recovery; no blanket reset/pay-again |
| Queue outage/worker crash/lease expiry/Calendar revoked | Persisted jobs rescued; appointment stays confirmed |
| Accepted-mail timeout,24h key expiry,bounce,duplicate delivery event | No blind duplicate send or false delivered claim; studio attention |
| Cancel/reschedule vs old worker | Suppress unsent old versions; record/correct in-flight race; no duplicate slot; refund distinct |
| Keyboard/reduced motion/320px/zoom/mobile keyboard | Usable stable controls/errors, no hidden required fields |
| Logs and URL audit; independent alert and restore exercise | No secret/PII leakage; real operator recovery evidence |

Existing003 suites are sources to adapt, not a declaration these tests passed for Sarsa. This planning turn executes no booking backend or payment tests; avoid importing legacy backend because import instantiates network/cache clients.

## 9. Self-review: weak assumptions corrected before handoff
- Removing modal only would leave backend token dependency: plan changes UI, model, route, hold transaction and tests together.
- Mandatory syntax is not verified identity: no verified marker or email-authenticated status route.
- Copying one-hold-per-email would enable victim lockout after OTP removal: scoped admission replaces that rule.
- Timer or checkout-dismiss event is not payment truth: server deadline and provider reconciliation decide.
- Sheets/Calendar success cannot substitute for durable slot ownership: database owns appointment state.
- Durable queue is not exactly-once external delivery: stable IDs, provider-window-aware retry and attention needed.
-003 confirmation mail waits for Meet: propose separate acknowledgement to avoid invisible paid appointments.
- A reference historical bug is not a current incident: audit labels dated fixes separately from current-source risks.
- Current design previews are not production proof: preserve separate HTML, backend, hosted/provider and owner-acceptance evidence.
- Strong outcome requires honest residual risk: anonymous abuse, mistyped contacts, lost receipt and third-party outage remain managed failure cases, not eliminated possibilities.

## 10. Inputs needed before real checkout, not blockers to visual planning
Approved service names/fees/taxes/durations; practice timezone/hours/horizon/notice; session mode and per-service birth requirements; public support channel and responding operator; cancellation/reschedule/refund rules; Sarsa-owned provider access; existing-booking inventory and cutover constraints. Do not request secrets in chat. Preserve unknowns as explicit configuration items; no invented business facts.

## Revision2 execution checkpoint
Implementation contracts C01–C08 now specify file/module seams, canonical state/actions, anonymous admission persistence, evidence-aware safe restart, exact notification dependency changes, routing/cutover and proof levels. The reference not_received projection was found insufficient for terminal-unpaid decisions. Do not copy its expired/not_received auto-reset. Contact and payment paths stay separately protected. Six page compositions remain; customer sees four simple steps. Plan is ready for owner review before execution, with provider-specific order finality, anti-abuse provider/limits and client service/reminder/operations inputs explicitly open before real checkout.

## Improvement tracking and later project003 retrofit
Maintain [the004-to-003 improvement register](004-to-003-improvement-register.md) during each implementation slice. Entries are planned until implementation and evidence are linked. Shared fixes need separate003 compatibility review; Sarsa policy changes do not transfer automatically.

## B2 outcome —21 September2026
Owner approved revision2. Local automatic Booking experience implemented in [16](../16-automatic-booking-experience/), with verification and improvement-register updates. This completes the HTML demonstration checkpoint, not the real booking backend. The owner subsequently accepted16. Next execution follows revision3 E1–E6 directly into the permanent system.
