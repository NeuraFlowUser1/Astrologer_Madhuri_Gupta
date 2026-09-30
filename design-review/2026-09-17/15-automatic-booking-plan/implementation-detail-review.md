> Current execution authority: [revision5 implementation plan](permanent-system-execution-plan.md),28 September2026. Earlier dated source inventories and B-stage sequences below are historical; revision5 and the resource manifest distinguish current implementation from pending hosted proof.

# Implementation detail review — revision4

22 September2026. Adds binding detail to revision3 permanent-system-execution-plan.md and C01–C08. Same one permanent implementation; no new mock stage, provider change or application implementation in this review. Where earlier text only limits unexpired holds, R4.1 additionally prevents a same-context unresolved checkout from being bypassed.

## R4.1 — Checkout ownership survives slot expiry

Problem: C03 says one active held booking/context. expire_holds in003 frees the slot and marks expired. C04 rightly keeps an exposed order unresolved. Without a separate guard, a new request in a second tab could pass the hold-only rule while the old payment is still uncertain. The UI disabling its own Pay button cannot enforce this across tabs or retries.

Design: checkout_contexts gains active_checkout_id (nullable FK to the checkout/booking) with a consistency constraint established by transaction code; the context row is locked when admitting or releasing a checkout. One context points to at most one unresolved checkout. This is separate from slot_claims and from whether an appointment is confirmed. Store a checkout resolution reason and resolved_at, not a second ambiguous payment-state enum. Set the pointer atomically with booking/order intent. Retain it for creating, creation_unknown, payable hold and unresolved exposed order after expiry. Clear it only after a confirmed captured appointment, a documented C04 safe abandonment, or authenticated studio resolution. An extra review payment on an already-confirmed booking remains an independent financial case; it does not retroactively invalidate that appointment.

Request flow: validate formats and authenticate context/receipt → persist rate admission attempt under context/request id → acquire locks in fixed order (context, schedule, booking/order rows) → expire slot claims as appropriate → compare active checkout and request fingerprint → create/resume or reject → commit → contact provider outside transaction. Recovery/finalizer paths needing context pointer updates use the same lock order, obtained from immutable booking context identity before locking; no schedule→context inversion. Keep existing schedule-first003 paths from being copied unchanged into that new order. Global hold-expiry cleanup may free claims under the schedule lock but must not update context pointers in that loop; resolution that clears a pointer follows the context-first order separately. Foreign keys must restrict deletion of referenced context/financial records rather than cascade-delete them. Test deadlocks with concurrent admission/finalization/expiry.

Duplicate same request/body/receipt returns existing outcome without extending expiry or counting twice. Same request with changed body is409. New request while pointer unresolved returns checkout_in_progress. Context cookie alone cannot retrieve the earlier booking ID, customer data or receipt secret; valid existing receipt is needed to resume. If receipt is lost, display “A payment may still be in progress in this browser. Please contact us before starting again.” No email-only recovery. A fresh rotated context is not provably the same human; acknowledge that limitation and use bounded abuse controls rather than claiming universal cross-device duplicate prevention.

Context expiry cleanup must retain/restrict referenced rows while money/work remains unresolved. Expired cookie must not invalidate an independently valid receipt. Existing receipt recovery stays available if new context creation/admission is unavailable. Two-tab tests: same context + new request; copied sessionStorage receipt; lost storage; hold expiry while provider response arrives; context expiry with unresolved case. Prove at most one unresolved admitted checkout/context and no lost financial case.

## R4.2 — Persisted financial evidence and notification intent

Keep003 PaymentEvents.receive's useful pattern: validate raw-body signature and expected account; persist event identity/hash plus processing job in one transaction before acknowledging a supported event. A queue publication failure does not roll back acknowledged durable work: scheduled rescue republishes it. Database failure must not return a successful durable receipt. Same event ID/same hash deduplicates; different hash alerts/rejects. Unknown supported-field shapes go to explicit attention/retry handling, not guessed success.

Canonical finalizer atomically records unique financial observation, appointment/claim decision, context-resolution update and notification intent. C06 event_key fixes distinct-payment notification conflicts; do not catch an insertion error and return confirmed while silently dropping the job. On transaction failure, retry from persisted inbox/provider observation. For browser-only verification during DB outage, return checking; bounded server reconciliation must independently rediscover payment. Match order, merchant, mode, integer minor-unit amount, currency, captured/refund facts; never browser success text.

If captured payment is observed after hold expiry, do not backdate ownership from provider timestamps or reclaim another visitor's slot. Retain the money case and explain that confirmation requires review. That is the chosen conservative policy, even if the payer started earlier. This needs explicit final UI copy and operator resolution, not an indefinite spinner. Partial refunds and disputes remain separate financial facts; cancellation is not proof of refund.

## R4.3 — Recovery when credentials rotate

003 PaymentCheckout._pinned currently compares literal key_id and mode with the single configured provider. C04 said preserve recovery after rotation but did not specify the mechanism.

Persist merchant identity, environment, order ID and originating credential version with each order. Credential configuration has bounded named versions, secrets in approved secret storage only, with explicit retirement dates and access audit. Normal new orders use the current version. Recovery selects only a configured credential authorized for that same merchant/environment; it never tries unrelated accounts or modes. A newer key for the same merchant may be used only after provider-supported access to the original order is verified. Do not assume revoked credentials can work or that cross-key access exists.

Before rotation, inventory outstanding orders/events and prove original-order lookup with the intended replacement where supported. Keep a documented overlap for webhook-signature verification if provider configuration supports it; use a small bounded allowed-secret set, not accept-any fallback. Original merchant identity remains pinned even when authentication changes. If required access is unavailable, retain the case, mark account_connection_needed and alert the operator; never create a replacement order as recovery. Queue jobs store resource/credential version identifiers, never secrets. Apply corresponding explicit connection-version handling to Calendar and email destinations; a changed Calendar must not recreate an existing meeting blindly.

## R4.4 — Schedule authority and manual appointments

Database transactions can prevent conflicts inside the booking system; they cannot atomically prevent someone independently adding a meeting in Google Calendar at the same moment. Previous planning must not imply otherwise.

Before public opening choose and document the practice's scheduling rule. Recommended first release: booking database owns offered appointment capacity; staff enter manual appointments/closures through the protected studio path before promising those times. Import existing commitments at cutover. Calendar is a meeting/delivery destination, not a second uncoordinated reservation authority. Calendar changes made outside that process are surfaced for operator reconciliation; they must not silently delete a paid booking.

If the practice requires external Calendar edits to immediately control availability, treat that as a concrete additional integration requirement: bounded busy-data freshness, change detection, outage behaviour and reconciliation must be implemented and tested before claiming it. A fresh fetch alone cannot eliminate the final cross-system race. Explain that residual operational constraint rather than promising impossible atomicity. No multi-practitioner engine is needed without an actual requirement.

Keep UTC instants plus the explicit approved practice timezone and service duration snapshot. Quotes bind service/config version, amount/currency/duration, eligibility and expiry; availability binds service/date/policy version. Hold revalidates policy and exact interval. Changed fee or incompatible time returns fresh review and preserves unrelated fields; it never silently buys a different service. Unknown business values keep the relevant service unavailable, not zero-priced or populated from demo data.

## R4.5 — Explicit modules and route integration

Proposed004 production seams (create/adapt inside004, never import runtime code from003):
- backend/booking_engine/application.py: final app factory, narrow readiness/intake policy, route registration; api/index.py explicit entrypoint.
- models.py/domain.py/policy.py: shared public schema, approved catalogue/time rules and structured errors; BookingDetails independent from Contact VerifiedInput.
- storage.py + migrations/: transactional holds/claims, context/admission, receipt access, financial observations and outbox; SQL version compatibility.
- payment_checkout.py, payment_events.py, razorpay.py: explicit provider boundary, durable order intent, signed inbox and canonical finalizer.
- booking_delivery.py, inquiry_dispatch.py, workers/booking-delivery/: adapted message/calendar handlers, durable publication, authenticated consumer and rescue. Keep Contact job routing compatible; a client-local worker may handle both with explicit allowlists rather than creating duplicate queues by default.
- frontend/src/booking/: bookingState, bookingApi, bookingPolicy, useBookingSchedule, bookingReceipt and BookingExperience from C01; actual /#/booking route imports this instead of the legacy page after integration checks.

These paths are implementation ownership seams, not a requirement to invent a new abstraction per file. Reuse smaller existing modules where boundaries are already clear. No general event framework, generic multi-provider platform or second admin application. The production build must exclude design-review demos/test fixtures and their reset/scenario controls. Inspect actual build roots/output, not just source filenames. Preserve current public links and Contact policy; remove Render warm-up/fallback only with callers migrated and tested.

Contract response envelope: stable code, field errors, next_actions and minimal state; no raw provider/SQL error in customer UI. Generation/request guards cover both availability and quote responses. Conflicting/stale response version cannot overwrite a newer selection. Unknown response/state => recoverable checking/error, never auto-confirm/reset. Add schema contract tests between Python output and frontend fixtures; fixtures are checks of final code, not a mock customer service.

## R4.6 — Customer actions without internal complexity

| Situation | Plain-language message | One primary action |
| --- | --- | --- |
| Time taken before checkout | That time was just taken. Please choose another. | Choose another time |
| Price changed before hold | The price has changed. Please check the new total. | Review total |
| Payment window closed | Let’s check what happened to your payment. | Check payment status |
| Waiting for a reliable answer | We’re still checking. Please don’t pay again. | Check status, with rate-limited server refresh |
| Check has failed repeatedly | We couldn’t finish checking your payment. Your reference is shown below. | Contact support; background recovery continues |
| Paid/meeting delayed | Your appointment is confirmed. We’re preparing the meeting details. | View appointment |
| Email failed | Your appointment is confirmed, but the email could not be delivered. | View appointment, secondary help |
| Saved access lost | We can’t safely open this booking here. | Contact support |
| Controlled verification closed/public not yet open | Online booking is not available yet. | Contact the practice |

Status freshness is readable, not a rapidly updating timer; slow bounded polling pauses when hidden and refreshes on return. Do not announce every countdown tick to screen readers. A hold countdown begins only after server confirmation and never extends on reload. Respect reduced motion, keep focused fields stationary, and never hide payment errors behind choreography. On uncertain status stop animation loops that imply imminent success; show reference/support. No database, queue, token or webhook vocabulary in customer copy.

No mandatory marketing consent, account creation, OTP or additional form step. Unknown birth time/preparation fields are configured only when the service actually requires them. Required contact details are not labelled verified. Personal data is not stored in URLs/browser drafts/analytics; only minimal opaque receipt material is stored in the real implementation. Errors and logging redact body values and secrets.

## R4.7 — Implementation evidence and release conditions

Map each E1–E6 item to its changed files, schema version, non-secret permanent resource identity, build/test/provider evidence and unresolved exceptions. Use the existing improvement register, not another competing tracker. Extend proof with R4.1 multi-tab/context lifetime tests, lock-order tests, credential rotation, durable webhook acknowledgement, changed policy/stale quote, and manual-calendar authority tests.

Restore exercises and injected database/queue/provider failures happen in safely isolated test execution, not on the live customer database. Checks exercise final production modules. For permanent controlled acceptance, allow only designated recipients/appointments and preserve a real financial audit trail. Readiness must cover migrations, current service configuration, authorized provider identity, scheduler/worker health, and supported operator recovery; transient delivery failure leaves already-paid booking confirmed and recoverable.

Do not declare “enterprise-grade” from a plan. Completion means demonstrated invariants and documented operational limits. No execution/real-account inspection/customer-data access occurred in this revision. Account-specific capabilities, pricing/minimum payment, reminder rules and business settings remain explicit pre-activation inputs.

## Review result

Pass1 traced003 hold/expiry/payment preparation and payment inbox plus existing004 integration plan. Pass2 challenged concurrency, lost access, credential rotation, calendar authority and downstream notification failures. Pass3 checked simple customer actions, module ownership, current-document consistency and evidence boundaries. Key strengthened areas are contracts requiring tests, not claims of newly observed live failures or implemented fixes.
