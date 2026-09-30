> Current execution authority: [revision5 implementation plan](permanent-system-execution-plan.md),28 September2026. Earlier dated source inventories and B-stage sequences below are historical; revision5 and the resource manifest distinguish current implementation from pending hosted proof.

> Revision4 specifics: [implementation-detail-review.md](implementation-detail-review.md). In particular, one unresolved checkout/context is enforced separately from one unexpired slot hold; use fixed context→schedule→booking/order lock order across all paths.

> Revision3 execution authority: [permanent-system-execution-plan.md](permanent-system-execution-plan.md),22 September2026. C01–C08 remain correctness contracts. Build their final wiring together in the permanent system; old B3→B4 sequencing is superseded. No additional mock product. Controlled activation/real-payment rules are in revision3.

# Booking implementation contracts — revision2
21 September2026 · Reviewed specification, not implementation

Read with plan.md. This is the concrete implementation companion, not an independent roadmap. If a broad sentence in plan.md is ambiguous, these contracts define the intended behaviour. No application/provider code was changed in this pass. Owner confirmed “outreach” means website booking and notifications.

## C01 — Visitor journey and interface boundaries
The customer sees four plain steps: **Consultation → Date & time → Your details → Review & pay**. Six designed page compositions are not six mandatory forms. Completion appears in the review area. No account, site OTP or forced Contact detour.

One client state owner controls draft, policy/quote, selection and checkout. In the future React integration use a reducer with explicit events, not independent booleans such as paid/success/expired that can contradict each other. Suggested modules below are proposed new Sarsa files, not existing files:
- frontend/src/booking/bookingState.js: pure transition rules, canonical draft, request generation and view selection.
- frontend/src/booking/bookingApi.js: same-origin transport, timeout, stable error parsing, receipt headers; never changes booking truth.
- frontend/src/booking/bookingPolicy.js: schema/compatibility checks and shared test fixtures for field/date/quote rules.
- frontend/src/booking/useBookingSchedule.js: abort/generation-guarded reads, independent refresh status.
- frontend/src/booking/bookingReceipt.js: versioned Sarsa storage namespace, opaque request ID and32-byte random secret only.
- frontend/src/booking/BookingExperience.jsx and section components: visuals and accessible controls; cannot confirm payment themselves.
Use the existing React/Vite stack and installed libraries where suitable. No new UI framework, generic workflow platform or second application.

Draft changes increment generation. An asynchronous result is accepted only for its date/service/generation and, for payment, its original request ID. An old response must never repaint a new selection. AbortController is a performance aid, not the correctness mechanism. Background refresh keeps visual content steady and tells the visitor “Checking these times…”; final progression waits for fresh valid state. Date or incompatible service change clears the time, not the contact draft. Do not reset a valid slot on an unrelated keystroke.

Before payment, Edit links return to the relevant field with existing values. During checkout creation, one submission is in flight; further clicks share that request, and editing is temporarily unavailable with a reason. After an order is exposed, use C04: do not launch a new request on Edit while old money may be pending. Refresh with receipt resumes the saved minimal appointment/payment summary; it does not pretend to restore a sensitive draft that was never stored in the browser. Re-enter information only for a genuinely new checkout, never to view an already-paid result.

UI text/action contract:
| Condition | Visitor-facing wording | Primary action |
| --- | --- | --- |
| Availability loading | Checking available times… | None; retain readable selection context |
| Availability error | We couldn’t load the times. Your details are still here. | Try again |
| Full date | No appointments available on this date. | Choose another date |
| Slot lost | That time was just taken. Please choose another. | Choose another time |
| Fee changed | The price has changed. Please review the new total. | Review updated total, never auto-pay |
| Hold exists | This time is reserved for you for… | Pay [server total] |
| Payment uncertain | We’re checking your payment. Please don’t pay again yet. | Check payment status |
| Confirmed | Your appointment is confirmed. | View appointment details |
| Meeting pending | Your appointment is confirmed. Meeting details are being prepared. | Check details |
| Email failed | Your appointment is confirmed, but we couldn’t deliver the email. | View details / contact support |
| Access receipt missing/expired | We can’t safely open this booking here. | Contact support; no email-only lookup |
No database/queue/webhook/idempotency/lease vocabulary in product UI. One dominant next action per state. Reference number visible and copyable; never call it a tax invoice. Field errors are text-associated, not colour-only. Country selection and mobile entry are one understandable group. Explain required email/mobile use in one sentence: “We’ll use these for your appointment details and any booking issues.” No marketing or SMS promise.

## C02 — Code integration and dependency map
Do not wire the designed page back into the legacy confirmation endpoint.
| Layer | Existing evidence | Sarsa implementation and dependent checks |
| --- | --- | --- |
| Application routes |004 frontend/src/App.jsx uses HashRouter | Preserve existing /#/booking?service=... and /#/contact entry routes in first production integration; service parameter allowlisted. Prototype relative URLs never ship. Route migration/SEO is separate scope, not a silent router replacement. |
| API origin |004 Booking.jsx and App.jsx fall back to Render; vercel.json rewrites everything to index.html | Target same-origin /api, with API rewrite before SPA fallback and a real Python entrypoint in the permanent Sarsa project. Update Booking, Contact and warm-up caller together; if Contact not ported yet, explicit temporary per-feature routing with a documented removal date, not a hidden generic fallback. Prefer complete common transport cutover. Test /api returns JSON, not200 HTML. |
| Python structure |004 backend/main.py monolith and root main.py recursive ImportError fallback | Proposed isolated backend/booking_engine package adapted from003 src/backend. Explicit api/index.py entry and explicit app factory; remove recursive fallback during integration. Do not import both old/new apps or initialize two engines. Contact handler port keeps its own verification policy. |
| Checkout input |003 models.BookingInput inherits VerifiedInput | New booking-only input = BookingDetails + request_id; no verification_token. Contact VerifiedInput remains. Enforce both contact fields at boundary and hold validation. |
| Readiness |003 application.booking_ready checks OTP secret AND literal Kundan origin | Sarsa-specific approved origin/config, merchant pinning, store/dispatch/Calendar capability checks. Separate booking readiness from enquiry OTP readiness. Do not keep a literal003 origin or pretend a removed booking OTP is required. Contact may still require OTP settings. Fail closed for new checkout, preserve existing recovery handlers. |
| Checkout admission |003 Store.hold consumes verification and checks email-active hold | New context-bound admission/transaction C03; no victim-email veto. Keep receipt, request fingerprint, quote and slot invariants. |
| Payment status |003 storage.booking_status maps absence of local observations to not_received | C04 returns evidence-aware payment state + allowed actions. No UI reset based only on old not_received. |
| Notifications |003 storage.enqueue, BookingDelivery.KINDS, inquiry_dispatch.BookingDispatch, worker.mjs, migration CHECKs | C06 adds explicit message roles/kinds end to end, including budgets, observation, cancellation, backfills and runtime schema compatibility. |
| Frontend state/status |003 Appointment_Booking.jsx automatically clears expired/not_received | Replace with server-authorized restart predicate, not copied condition. API/UI enum contract tests mandatory. |
| Operations |003 private admin, payment cases, recovery heartbeat, sheets and backup | Adapt with Sarsa identities; no new public administrative endpoints. Monitoring filters and restore test must recognize new schema/job kinds. |

Read-only reference003 files remain untouched. Copy reusable behaviour/tests into004; replace client identity through one configuration boundary (branding, origin, catalogue, staff destination, provider IDs), never find/replace credentials. New paths listed here are proposed; verify/create them within004 during execution. Reference BookingDispatch actually lives in inquiry_dispatch.py, not a separate booking_dispatch.py.

## C03 — Anonymous checkout admission, credentials and schema
Receipt: UUIDv4 request ID +32-byte cryptographically random secret, generated before first mutation. Hash purpose+request ID+secret in database; validate in constant time. Keep secret out of logs, links, email, queue messages and third-party analytics. API exposes only receipt-authorized minimal booking data. HTTPS, no-store, exact CORS origins and request body limits. Use a Sarsa-specific receipt key so another client/preview cannot resume it accidentally.

Anonymous context: first-party server-issued random context in Secure/HttpOnly/SameSite cookie, proposed24h expiry; it is an abuse grouping, not identity or an account. Same-origin context creation endpoint returns no customer facts; context cookie alone never authorizes reading a booking. Bind one active hold and a separately persisted unresolved-checkout pointer to the context transactionally as specified in R4.1. Validate Origin on browser mutations; signed provider webhooks and authenticated worker routes have their own authentication and are not rejected for lacking browser Origin. If required cookie is blocked, explain inability to start secure checkout and offer support; already-issued valid receipt may still recover its booking. Prevent CSRF and untrusted forwarded-IP input. No secret hidden in a query string or default fixture.

Suggested local schema additions in Sarsa migrations:
- checkout_contexts(id/digest,expires_at,created_at) with bounded expiry cleanup.
- checkout_admissions(context_id,request_id,receipt_digest,request_fingerprint,outcome,created_at); unique request_id; outcomes pending/rejected/committed. Dedupe rate counting for a retried identical authorized request; different fingerprint/receipt is a conflict. Admission tokens never mean verified email.
- bookings.checkout_context_id and indexes/constraints supporting one active held row per context. Expire holds within the schedule transaction before uniqueness check. Existing email lookup index is only an index, not a unique constraint; remove the EMAIL RULE in Store.hold, not imaginary uniqueness DDL.
- booking_revision integer and explicit provider/order observation timestamps/status. Durable case linkage survives customer receipt expiry.
Rate counters are committed even if subsequent hold transaction fails. On crash after admission but before booking write, the same request may finish once without paying quota twice; concurrent starts serialize context+request and schedule claims in fixed lock order. Never trust client “already admitted.” Server validates admission ownership/fingerprint again inside hold transaction. All independent database workers use same ordering; test deadlocks/retries.

Initial risk limits remain load-test proposals, not launch guarantees. One active hold/context and the independent unresolved-checkout guard in R4.1 are hard invariants within an authenticated checkout context. Context creation is rate-limited too. Excess risk -> short Retry-After or managed bot check, with explicit accessible failure path; the provider/thresholds must be chosen and proved during final implementation E2–E6, not invented in HTML. Do not add email/mobile ownership challenges. Limiter unavailable blocks new holds while payment webhooks/reconciliation continue. Counter expiry/retention/cost limits must be bounded; never log raw email/phone as a risk key.

Receipt is a bearer credential: a person who steals a valid secret may exercise its limited authority. The prior “stolen receipt rejected” test expectation was impossible. Test wrong/missing/revoked/expired receipts instead. Restrict what it can do: resume/status and submit provider proof; no self-service cancellation/refund/contact-address mutation in first release. Prefer no marketing scripts on checkout, escaped content and compatible restrictive CSP. Retain reference expiry policy only after reviewing support needs; proposed end-of-appointment+24h for customer view, no automatic extension. Financial reconciliation continues independently after expiry; lost access goes to authenticated studio support, never silently disappears.

## C04 — Payment evidence and safe restart (critical correction)
Reference storage.booking_status currently derives not_received from no accepted/review entry in local payment tables. PaymentCheckout.authorized/resume does not itself fetch the provider. Therefore expired+not_received is not sufficient proof that a payment did not happen. This is an adaptation risk, not a claim about an observed live003 loss.

Canonical response has independent fields:
- appointment_state: held / confirmed / expired / cancelled / payment_review.
- order_state: not_attempted / creating / creation_unknown / ready / failed.
- payment_state: unobserved / pending / captured / failed_observed / refunded / needs_attention.
- payment_checked_at, payment_evidence_source, server_now, hold_expires_at.
- next_actions from server: resume_payment, check_status, choose_new_time, contact_support. Server is authoritative; UI cannot infer a safe action from an enum alone.
- customer_message_code; meeting state; separate acknowledgement and meeting-email delivery states. Never include raw provider errors or secrets.
Contract tests reject unknown/contradictory responses and retain a recoverable checking view.

Evidence policy:
1. No order creation ever attempted: expired hold may safely permit new selection. Server serializes abandonment with prepare() so a stale worker cannot create an order afterward.
2. Order creation definitely rejected, with authoritative evidence no order exists: new selection may be allowed under a stored reason. Ambiguous transport/server error is not definite rejection.
3. Order created or creation response unknown: keep receipt/case, reconcile original provider order/payments. An empty payment list is only “no payment observed at this check.” It does not prove an exposed checkout cannot complete later. A failed individual attempt also does not close the whole order.
4. Do not automatically clear/exchange an exposed order merely because hold expired. Require a documented provider terminal/non-payable condition OR authenticated studio-reviewed resolution before issuing choose_new_time. Provider capability to expire an order is not assumed. If unsupported, visitor gets stable checking/help and operator resolves; do not leave an endless spinner or unowned case. Studio authorization, reason and superseded-order linkage are recorded. Residual late money remains visible even after reviewed resolution.
5. A retry while SAME hold/order is payable resumes that order after reconciliation. It does not create a second checkout or reset deadline. Close SDK/window does not change payment truth.
6. Captured amount can legitimately become refunded later: preserve financial chronology. Appointment state changes only through explicit cancellation/exception rules, not a generic “never downgrade” guard that ignores refunds.

API design:
- POST /api/checkout-context creates/reuses admission context.
- POST /api/checkout takes validated draft+quote_version+request_id and receipt header. Returns200 ready or202 checking, with server next_actions;401/403 access,409 field/slot/quote conflict,422 fields,429 limit,503 new-checkout unavailable. Same ID/body/receipt is idempotent; no new-order retry wrapper.
- POST /api/checkout/resume authenticates receipt, returns stored projection and initiates one bounded/coalesced refresh if due. No external I/O under schedule lock. Mark freshness; return202/check_status while unknown. Do not blindly invoke provider on every poll.
- POST /api/checkout/verify-payment and signed payment webhook feed the same server-fetched finalizer. Current provider account/mode must match pinned order; credential rotation requires continuing reconciliation for original account, not rejecting old paid cases indefinitely.
- GET /api/booking-policy + /api/availability and quote endpoint use approved schema/version; validate service/date associations and server time. No fake backend fallback.
- Do not introduce an automatic abandon endpoint for exposed orders in first release. Studio resolution is explicit; all legacy creation aliases return410 after client migration, not unpaid confirmation.

Reference background reconciliation only selects within starts_at+24h and one order per invocation with5min revisit. Do not copy this as a universal recovery guarantee. For Sarsa: persist unresolved-case next_check_at/attempts/owner until resolved; prioritize money-bearing/near-session cases, avoid starvation with bounded fair batches and indexes, and use measured worker cadence. No case is deleted just because customer receipt expired. Keep provider usage bounded/backoff; monitoring shows oldest age and missed sweep heartbeat.

## C05 — Editable details, timing and data validation
UI and API share fixtures for valid/invalid names, email/mobile, service/date/timezone and birth requirements. Python remains authoritative. Email normalization must be consistent with source and reviewed provider behaviour; no silent typo correction. Country-aware phone parser chosen explicitly during E2/E5; existing0037–15digit regex is a format baseline, not country/mobile verification. Do not hand-code global numbering rules or add heavy services for this form.

Reference code hardcodes30min in several places (model Literal, hold SQL, policy, availability, end time). First real release can retain30min only if approved for all offered services. Otherwise a separate consistent duration/capacity schema change is required before enabling a variable duration; never change one UI label while leaving fixed SQL. Birth requirements are likewise service-configured; block approval of real schema until known. Do not make every service require invented birth time.

Hold time based on database UTC timestamps, displayed in explicit practice timezone. Client display uses server_now offset + monotonic elapsed time; tab visibility change reconciles. Local clock change cannot extend hold. Timer hitting zero disables opening another payment attempt and requests status; it does not declare failure/refund. Min-notice/horizon/closures enforced at hold, not merely greyed-out calendar.

Once payment starts, details immutable for that checkout. Before a provider order is attempted, safe draft replacement uses a new request only after C04 abandonment. After capture, initial release routes contact correction/rescheduling to authenticated studio, with revision/audit; no public destructive action based only on a bearer viewing receipt. Support checks merchant records and independent evidence; name/email/phone/reference alone cannot authorize disclosure or edits. If identity cannot be resolved, no sensitive facts disclosed.

## C06 — Notification design with actual downstream constraints
Concrete proposal: three mail jobs per normal booking, not an unspecified “extra email.”
| Job kind / recipient role | Created by | Depends on | Content |
| --- | --- | --- | --- |
| booking_ack / customer | Confirmed-payment transaction | Confirmed appointment, not Meet | Minimal appointment/payment acknowledgement; no birth data/notes |
| booking_ack / client (studio owner) | Same transaction | Same | Paid booking reference and private-studio instruction |
| booking_calendar / calendar | Same transaction | Approved meeting mode/connection | Deterministic Calendar/Meet creation; no duplicate provider invitations |
| booking_details / customer | Atomic ready-meeting write | Confirmed current booking revision and ready meeting | Current appointment and join details |
| booking_cancelled / calendar,customer,client | Authorized cancellation transaction | Recorded cancellation | Calendar removal + accurate cancellation; refund separate |
| payment_review / client | Financial exception transaction | Preserved observation/case | Attention, no false booking |
Sheet jobs retained separately. These are proposed Sarsa kind names; reference supports fewer kinds. Baseline acknowledgement is queued promptly, not promised instantaneous delivery. For approved non-video session mode, skip Meet and give relevant confirmed instructions; do not create misleading video links.

Normal appointment job identity=(kind,booking_id,recipient_role,booking_revision), unique in database and provider key. Financial exception jobs additionally require event_key (provider payment ID or stable financial case ID). Add non-null event_key with empty default for normal jobs; migrate the uniqueness constraint to include event_key and carry it through dedupe/provider keys, status queries and dispatcher payloads. Backfill existing review jobs from their recorded payment suffix with an audited mapping; ambiguous historical rows require explicit review, not guessed association. Repeated delivery of the same event deduplicates; different payment exceptions on one booking must each persist. Source003 storage.enqueue varies suffix, while migration005 delivery_recipient_version excludes it: a second distinct payment_review on the same booking/version/recipient can conflict on that other index and abort the surrounding payment transaction. This is a static source finding, not a reproduced production incident. Test against the fully migrated local database before finalizing the migration. Store immutable payload/destination at first dispatch, provider ID, first-attempt time, uncertainty, next attempt, lease token and expiry. Lost response retries same payload/key while provider permits; no routing to SMTP. A known hard rejection and an unknown accepted send are distinct. Unknown beyond24h idempotency window becomes attention/reconciliation, not an automatic resend; delivery is not guaranteed exactly once.

Required migration and code changes as one slice:
- foundation/013 kind+recipient CHECKs; version/dedupe uniqueness; backfill explicit only, never mass-send old confirmations.
- storage.enqueue/current confirmation finalizer and calendar-ready transaction; add cancellation suppression of pending old revision.
- booking_delivery.KINDS, message factory, claim/run/finish; do NOT let its existing “anything not booking_confirmed means calendar cancel” branch handle a new kind.
- inquiry_dispatch.publish_jobs allowlist and BookingDispatch.kinds; workers/inquiry-delivery/worker.mjs allowlist/routing; authenticated delivery endpoints and scheduled rescue.
- email quota: normal booking now3mails instead of2, plus cancellation/failure jobs; account capacity checked before production. Accepted work must not vanish when allowance exhausted; defer and alert.
- booking_status projection, private studio attention queries, provider event correlation, counters, backup/restore and tests recognize new kinds. Do not collapse “latest customer job” into one email status.
- email acknowledgements/order may arrive out of order: meeting details is self-contained and does not rely on the acknowledgement arriving first. Do not block time-critical join details behind bounced/delayed acknowledgement. Hard-bounced recipient suppresses futile automated repeats and surfaces support.

Before claiming a job and just before external send, check current appointment/revision. Claim token fences stale worker DATABASE writes; it cannot retract a message already handed to a provider. Cancellation/contact-change racing in-flight mail can still deliver an older message. Record this possibility, suppress unsent stale jobs, send a current version correction when appropriate, and show current truth in protected booking view. Never promise “stale worker can never send old details” absolutely or hold a database lock across provider I/O to fake that guarantee.

Reminders: confirmed scope includes assessing booking notifications/reminders, but no independent automated reminder sender is verified in reference (Google default reminders are not customer reminder proof). Initial plan promises confirmation + meeting details only. Record reminder channel/timing/quiet hours/late-booking and cancellation policy as a separate explicit decision before implementing or advertising reminders. No SMS/WhatsApp/marketing automation implied by mandatory mobile.

## C07 — Operations, cutover and proof boundaries
Sarsa permanent project only; no copy of003 accounts. Configuration manifest lists origins, app identity, catalogue, runtime DB/migration roles, email sender/owner recipient, payment merchant/mode, Calendar connection, queue destination/environment and authenticated worker URLs; secret VALUES live only in approved settings.

Cutover sequence: verify existing booking inventory under separately authorized read access → freeze legacy new-booking intake for a short announced interval while reconciling → map existing commitments to protected slot claims (payment unknown stays unknown, never fabricate paid status) → deploy compatible schema/worker/API → verify correct origins/JSON routes/readiness/rollback → switch frontend/CTAs → retire both legacy creation aliases and unintended fallback hosts → retain appropriate historic lookup/support and financial handlers. If inventory or overlap policy unresolved, do not turn on real paid intake. Source existing legacy availability permitting overlap2 is not permission to import conflicting appointments silently.

Rollback: previous compatible UI can show “booking temporarily unavailable”; never restore unpaid legacy confirmation endpoints. Payment callbacks, webhook acceptance, reconciler and outstanding delivery must stay live. Versioned job/schema rollout must allow old queued work to drain; do not remove old kinds until no work references them. Backup is evidence only after a safe restore exercise, not file existence. Keep immutable financial records under approved retention; don't roll back money with frontend.

Alert thresholds from plan are proposed detection targets. Reference recovery cadence can exceed2min; do not promise2min detection with a15min sweep. Measure frequency, backlog throughput and actual operator coverage; tune targets or build necessary monitoring before claims. Independent notification route for sender outages; current operator with escalation instructions required. Bound poll rates and fair worker batches; service/API failure distinguishable from no availability.

Evidence, not separate product stages: completed B2 proves UI only. Tests of the final database and production modules prove selected invariants; controlled checks of the actual permanent connections prove provider behaviour; delivery/restore/operating evidence closes readiness. Testing remains part of the final implementation, not a mock-wiring milestone. Any real charge/messages require the concrete later authorization described in revision3. No production promise based on screenshots or one successful small payment.

## C08 — Focused test additions from revision2
- Expired/no local payment row + remote captured payment: must show checking/captured attention, never reset; cover delayed webhook and receipt refresh.
- Created/exposed order + empty provider payments, failed attempt or incomplete listing: no terminal-unpaid assumption; action restricted by C04.
- Crash before/after admission commit, before hold, after order attempt: identical authorized retry exactly one admission/hold/intent; different body/secret rejected.
- Two tabs same context, two contexts same slot, old API response after new date: one valid owner, no stale selection.
- Receipt revoked/expired/wrong/missing vs stolen-valid limitation; minimal projection; no browser storage draft leakage.
- New mail kinds accepted by SQL, dispatcher, worker and runner; unknown kind rejected; calendar create never falls into cancel branch.
- Calendar ready before ack, ack bounce, message acceptance timeout near24h, cancellation while send in flight: honest state and bounded correction, not impossible zero-race assertion.
- Contact OTP retains protection while Booking does not call/request it; booking readiness no wrong-client literal/OTP dependency.
- API route returns JSON not SPA HTML; old Render health warm-up/fallback removed; both legacy booking aliases disabled after migration.
- Reschedule absent public feature is not falsely demonstrated; studio correction versioning actually tested if added.
- Thirty-minute schema compatibility or complete approved duration change; timezone/date tests at midnight and device clock change.
- Recovery after appointment+24h and expired receipt retains unresolved financial case; independent operator access.
- Paid acknowledgment invoice wording does not imply tax receipt; no mobile reminder promise; each error screen has one clear action.

- Financial exception identity: two distinct review payments on one booking persist independently; repeated same payment creates no duplicate; notification insertion cannot discard the second financial observation. Verify migration/backfill and real database constraints, not just mocked enqueue.
