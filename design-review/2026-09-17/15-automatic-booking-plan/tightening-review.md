> Historical revision2 review. The current execution sequence is [revision3](permanent-system-execution-plan.md);16 is now accepted and no further mock-wiring stage is planned. Source findings below remain relevant.

# Tightening review — revision2 results
21 September2026. Additional read-only trace through003 payment preparation/resume/reconciliation, receipt functions, schema constraints, dispatcher/worker allowlists, Calendar/email delivery, readiness and004 routing. No implementation begun.

| Weakness in revision1 | Revision2 correction | Why the visitor benefits |
| --- | --- | --- |
| “Definitely unpaid” had no strict evidence definition | C04: local not_received is not final; server-authorized next actions, reconcile unknown/exposed orders | Avoid paying twice after a delayed response |
| Future modules/integration seams vague | C01/C02 specify state owner, API adapter, backend package, hash routes and same-origin cutover | Less rework; existing entry links continue to work |
| Six artistic sections could become six hurdles | Four customer steps, clear plain wording and one dominant action | An impressive page that remains easy to use |
| No-OTP admission lacked crash/retry schema | Context/admission records, transaction ordering, retry identity and authority boundaries | Fewer duplicate holds and fewer unfair blocks |
| Stolen valid receipt treated like invalid credentials | Explicit bearer limit, restricted actions, minimal data, support route | Honest protection and no false security claim |
| New email assumed to be template-only |3mail budget, kind/role constraints, enqueue/worker/runner/status migration | Paid work stays visible even if meeting creation is slow |
| “No stale email ever” implied impossible external atomicity | Version checks plus in-flight race/correction contract | Honest status and reliable correction instead of false guarantee |
| Readiness still inherited wrong client/OTP assumptions | Sarsa origins/config and separate booking/enquiry readiness | Removing booking OTP doesn't accidentally disable checkout or weaken Contact |
| Same-origin hosting had no cutover map | API precedence, remove Render fallback/warm-up, inventory old bookings, preserve recovery during rollback | No false200 HTML API responses or resurrected unpaid booking path |
|2min alert target ignored actual recovery cadence | Measure/scope worker cadence; unresolved cases outlive receipt/horizon | Nobody's paid issue silently disappears after24h |
| Reminder scope described as unanswered | Owner clarification recorded; reminder capability/policy explicit | No promise of reminders the system does not send |
| Mock preview acceptance included security proof | Separate HTML, deterministic database, hosted provider and operating evidence | We know what has actually been tested |

## New source evidence
-003 src/backend/storage.py:397–432 derives not_received from local payment dispositions; no provider freshness in that projection.
-003 src/backend/payment_checkout.py:authorized/prepare/reconcile_creation/reconcile_one: resume authorization does not establish terminal unpaid; attempted order creation is durable; unknown searches do not permit recreation. Reconcile selection bounded to appointment+24h and one due order.
-003 src/lib/requestReceipt.js creates UUID +32byte secret and stores only opaque receipt; storage.py check_receipt is bearer-based with expiry.
-003 src/backend/migrations/004_active_checkout_lookup.sql is a NON-UNIQUE email index; hold's email rule is Python/SQL lookup, not a unique-email DB constraint.
-003 src/backend/migrations/001_booking_foundation.sql and013_booking_delivery.sql restrict job kinds/recipient roles.005_inquiry_delivery.sql supplies per-kind/record/version/role unique index, uncertainty and lease fields.
-003 inquiry_dispatch.py contains BookingDispatch and publication allowlists; workers/inquiry-delivery/worker.mjs validates kinds. No booking_dispatch.py exists; proposed integration map uses actual paths.
-003 booking_delivery.py _claim/run/_calendar_create gates mail on Meet, snapshots payload, fences finish by lease; new kinds require explicit create/cancel branch handling.
-003 application.py booking_ready checks OTP and literal003 origin;004 App.jsx uses HashRouter and Render warm-up;004 vercel.json SPA catch-all does not define Python API routing.
-No general reschedule/reminder service was found by the scoped backend-source search. Historical/manual one-off work is not a product feature.

## Residual decisions, not hidden assumptions
Before real checkout: Sarsa fees/durations/birth requirements/schedule, operational support and reminder policy, context-risk provider/limits, provider order non-payability evidence or studio-resolution process, identity/config/provider access and existing-booking cutover inventory. These do not block synthetic HTML execution after owner review. They DO block claiming the real system is ready.

## External sources checked in this pass
[Resend idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys):24h duplicate protection requires bounded same-key retry. [Resend event types](https://resend.com/docs/webhooks/event-types): acceptance/delivery/failure are separate observations. [Razorpay order payments](https://razorpay.com/docs/api/payments/fetch-payments-orders/): supports per-order payment inspection; an empty read is not asserted here as a permanent order-cancellation guarantee. No live account or financial checks.

Additional final review: the003 payment-review dedupe key varies by payment ID but migration005 recipient/version uniqueness does not. C06 now requires financial event identity through persistence and delivery, with a real-database two-payment regression test before implementation is accepted. See IMP03 in [the ongoing improvement register](004-to-003-improvement-register.md). This is static source evidence, not a reproduced live incident.
