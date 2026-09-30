> Current execution authority: [revision5 implementation plan](permanent-system-execution-plan.md),28 September2026. Earlier dated source inventories and B-stage sequences below are historical; revision5 and the resource manifest distinguish current implementation from pending hosted proof.

# Project004 improvements and later project003 review

Updated21 September2026. Owner request: record every appointment-booking strengthening made for004 so applicable improvements can later be applied to003. This is the ongoing implementation register, not a claim that fixes are already built. No003 files are changed by this work.

## How this register stays trustworthy

For each implementation slice, add/update the stable entry below before handoff. Record actual004 files and commit (or dated local diff when uncommitted), relevant test/evidence paths, limitations, and any changed behaviour. Only mark proven after the named test passes at the stated level. Track local, hosted-provider and operational proof separately. Newly discovered improvements get new IDs; retain superseded entries with reasons. A planned benefit is not an implemented result.

Before a003 retrofit, re-inspect its then-current code and schema, reproduce the relevant risk in an isolated test, review existing records/queued jobs through authorized means, design compatible migration/rollback and obtain scoped execution authorization. Do not copy004 wholesale. No third-party calls or customer messages during local proof.

Backend entries below retain their historical planned status; see the28 September foundation update for implemented slices.003 remains not applied. The B2 update below records the local frontend work actually implemented and checked; it does not prove the planned backend protections. Source locations below are relative to003 AstroConnect unless prefixed004. Contracts C01–C08 are in implementation-contracts.md. Existing003 strengths reused unchanged are reference foundations, not claimed004 inventions.

| ID | Improvement and practical value | Source/evidence and implementation boundary | Required proof and transfer assessment |
| --- | --- | --- | --- |
| IMP01 | Evidence-aware payment recovery prevents encouraging a second payment while the first can still complete. | storage.py booking_status and frontend Appointment_Booking.jsx expired/not_received reset; C04 separates local observations from safe server actions. | Exposed order + empty/failed/incomplete observations never authorizes automatic new checkout. Shared reliability candidate; preserve003 OTP. |
| IMP02 | Persist unresolved financial cases beyond browser receipt life and normal appointment window. | payment_checkout.py reconciliation horizon/cadence; C04 durable pending-case scheduling with fair batches and alerts. | Old unresolved cases continue recovery without starving new ones; operator resolution audited. Shared candidate. |
| IMP03 | Save distinct payment exceptions independently instead of risking an index collision. | storage.py enqueue/confirm_paid; migration005 delivery_recipient_version ignores payment suffix; C06 adds event_key and migration/backfill. Static source interaction, not live incident. | Real database: two distinct review payments persist; same event deduplicates; migrated historical jobs remain dispatchable. Shared high-priority investigation. |
| IMP04 | Acknowledge a paid booking even while its meeting link is being prepared. | booking_delivery.py currently gates customer/studio mail on Meet; C06 split acknowledgement/calendar/details jobs. | New kinds/roles through SQL, queue, worker, budgets, status, cancellation and provider events; out-of-order mail self-contained. Shared product improvement for separate003 approval: more email volume. |
| IMP05 | Suppress obsolete pending notifications and handle unavoidable in-flight races honestly. | C06 version checks, immutable payload, fenced completion, corrective current details. | Cancel/reschedule while a send is in flight; never promise external exactly-once delivery. Shared candidate; first verify what003 already covers. |
| IMP06 | Show meeting, acknowledgement and delivery status separately with accurate next actions. | Current booking_status latest-customer-job projection; C01/C04/C06 explicit independent states. | Bounced ack, ready meeting, delayed details, confirmed booking all remain truthful. Shared candidate with UI adaptation. |
| IMP07 | Anonymous admission that cannot treat a typed email as proof of ownership. | storage.py hold email lookup; C03 context cookie, persistent attempts, purpose-limited bearer receipt. | Counters survive failed admission, concurrent holds, crashes, wrong/revoked secrets, cookie failure; stolen valid bearer remains a stated limitation. Primarily004 no-OTP adaptation;003 requires separate security design. |
| IMP08 | Required email/mobile at every booking boundary and shared validation cases. |004 frontend/backend mismatch in source-audit; C05 browser/server fixtures and number parsing. | Missing/invalid fields rejected without OTP; good international formats handled consistently.003 already requires both: verify rather than claim new requirement there. |
| IMP09 | Preserve choices safely and discard stale availability responses. |004 Booking.jsx date-change/fetch path; C01 reducer, request generations, quote/time invalidation. | Rapid date/service edits, refresh and errors cannot enable stale checkout; entered contact details retained where safe. Transfer only if003 regression test shows a gap. |
| IMP10 | Explicit application readiness and correct API routing prevent misleading partial launch. |003 application.py pins origin/OTP requirements;004 HashRouter/Render fallback/SPAcatchall; C02/C07 Sarsa configuration contract. | Correct API routing, no fallback to retired service, hash links preserved, Contact OTP still protected. Sarsa-specific adaptation; reusable configuration checks may benefit003. |
| IMP11 | Safe cutover and rollback preserve paid work, pending payments and queued messages. |004 legacy immediate-confirmation endpoints; C07 freeze/map commitments, compatible rollout, keep recovery alive. | Rehearsed migration/rollback with outstanding orders/jobs, no reopening unpaid legacy confirmation. Procedure reusable;003 migration must match its actual state. |
| IMP12 | Honest availability, timezone, price and capacity with durable delivery. |004 S01–S12 risks;003 already supplies much of this foundation. | Server-owned fees, atomic capacity, no invented slots, durable jobs, privacy-safe logs.004 improvement over its legacy code; do not mislabel as003 defect or new invention. |

## Policies that must not silently transfer

- No booking OTP is an explicit004 choice. Do not remove003 verification merely because004 does so.
- Mandatory phone/email are004 requirements and already present in003's reference contract; no invented003 gap.
- Contact enquiry verification is separate and unchanged.
- Sarsa identity, service catalogue, prices, schedule, appointment duration, meeting mode, support, reminder choices and privacy/retention decisions require client-specific values.
- The new acknowledgement/details split changes cost and message volume. Its003 adoption is a product decision as well as an engineering change.

## First execution handoff

B2 builds the local automatic Booking HTML and clearly labelled simulated recovery states. Record frontend improvements and browser evidence here. B3 implements and proves the engine locally, including IMP01–IMP03 adversarial cases. Provider and operational evidence comes later under B4/B5. Do not mark a backend risk fixed because its HTML simulation looks correct.


## B2 implementation update —21 September2026

Local implementation: ../16-automatic-booking-experience/{booking-model.js,journey.js,page.html,page.css,motion.js,review.js}. Uncommitted dated local work; no invented commit reference. Proof: booking-model.test.mjs (11 passing tests), verification.md and qa/ browser evidence in16.

| Entries | Actual004 progress | What remains before claiming a shared fix |
| --- | --- | --- |
| IMP01,IMP06 | Local UI distinguishes checking, held, confirmed, attention, safe restart and inaccessible receipt; same sample reference survives refresh. Close is not confirmation. Separate meeting/acknowledgement/appointment-email rows. | Real server-authorized actions, receipt authentication, provider evidence and notification truth remain unimplemented. |
| IMP08 | Both email/mobile required in HTML and local validation; errors and first-field focus verified. | Country-aware server validation, server-required contract and shared fixtures remain B3. |
| IMP09 | Implemented cleared stale time on upstream change, guarded asynchronous availability, preserved in-memory contact draft, prevented repeat checkout; browser/Node proof recorded. | Connect and re-test against actual policy/availability/quote API.003 applicability still requires its own audit. |
| IMP10 | Current local page links point to16; Contact booking copy updated while Contact enquiry policy retained. | Real application routes/readiness/provider identity unchanged. |
| IMP02–IMP05,IMP07,IMP11–IMP12 | Design contracts remain planned. Scenarios illustrate selected outcomes. | Database, admissions, worker, provider and cutover implementation/proof not done. |

Additional local improvements: keyboard time-selection focus retention; safe malformed-snapshot display; explicit sample-only storage with no contact/notes; reset/resume timing guard; measured contrast and mobile layout corrections. These are review-experience improvements, not evidence of corresponding003 defects. No003 retrofit performed.

## Revision3 planning update —22 September2026
Direct permanent implementation replaces the old isolated-engine-then-provider sequencing. Existing entries retain their evidence status. Add IMP13: independent closed/controlled/public intake while retaining payment recovery; IMP14: privileged expiring test quote bound to one authorized case, never public amount override; IMP15: compatible consumer/schema/producer cutover preserving legacy commitments. All three are planned, with no implementation or provider proof yet. Required tests and transfer boundaries are in permanent-system-execution-plan.md.003 adoption needs its own audit/authorization; small-payment operation and client settings are not automatic backports.

## Revision4 planning additions —22 September2026
IMP16: unresolved-checkout ownership beyond slot expiry, context cleanup and fixed lock order (R4.1);004 no-OTP adaptation,003 needs separate identity review. IMP17: credential rotation without stranding original payments/meetings (R4.3); shared candidate requiring account-capability proof. IMP18: explicit database/manual-Calendar scheduling authority (R4.4); operational agreement/integration requirement, not assumed003 bug. All planned/unimplemented; no003 changes. Durable signed inbox behaviour in R4.2 is an existing003 strength to retain, not an invented004 improvement. Link eventual file/migration/test evidence to these IDs during execution.


## 28 September — first permanent backend foundation

Local branch work/sarsa-booking-system; uncommitted004-only changes in backend/booking_engine, with psycopg and phonenumbers declared in root/backend requirements. No003 files changed.

- IMP01/IMP06: payment_policy.py implements conservative actions for unobserved/failed/uncertain exposed orders and separate appointment/payment state. Ten local tests (including parameterized subcases across security/input/policy) pass. Projection not yet wired to a public receipt endpoint.
- IMP03/IMP04: migration001 includes distinct event_key notification identity and explicit acknowledgement/calendar/details roles. Actual development PostgreSQL check accepts two financial exceptions and rejects duplicate identity/invalid recipient. Provider dispatch/delivery is not yet implemented.
- IMP07/IMP08: security.py receipt/request binding and models.py required email/mobile without OTP, with phonenumbers international mobile parsing. No context issuance, admission quota or public routes implemented yet.
- IMP12/IMP16: interval exclusion handles variable-length appointments and closures. Migration002 implements context-first start_order_creation and abandon_unattempted; schedule-only expiry retains context pointer. Actual database sequential checks pass. Full hold/finalizer and simultaneous-session deadlock/concurrency proof remain outstanding.
- IMP19: least-privilege NOLOGIN runtime group; schema/history/deletion denied and financial observations append-only. Verified database privilege queries. Actual login creation and host secret wiring pending; applicability to003 requires its own role audit.

Development only: project cold-art-76378232, branch br-still-mud-b38cy2py. Migrations001–003 recorded with SHA256; production branch br-cool-bird-b39eiccm still has no sarsa_booking schema. Tests rolled back synthetic rows, leaving zero bookings. No money, messages or customer records.


## 28 September — reservation and payment-core execution

Actual004 files: backend/booking_engine/policy.py, connection.py, storage.py, razorpay.py, order_creation.py, payment_evidence.py; migrations004–010; tests/test_policy.py, test_storage_boundary.py, test_razorpay.py, test_order_creation.py, test_payment_evidence.py, reservation_database.sql and calendar_database.sql. Uncommitted work on work/sarsa-booking-system. No003 edits.

- IMP01/IMP07: separate committed admission and reservation; retries reuse the same normalized binding, changed/missing bindings are rejected, pending payment ownership survives capacity expiry. Database comparisons explicitly use NULL-safe equality. Per-context counter survives reservation rejection; whole-site/context-creation rate protection remains unimplemented.
- IMP02: order creation records uncertainty without another external POST; unresolved orders remain due for recovery. Recovery consumer/scheduler and operator resolution still pending.
- IMP03: finalization tests create two distinct additional-payment cases/jobs for one confirmed booking without collision, while same capture deduplicates. Candidate shared fix now has real development database proof;003 source/data still requires separate review.
- IMP04: captured booking atomically enqueues two acknowledgements plus independent Calendar and client/agency Sheets jobs. Meeting details are deliberately not sent before a meeting exists. Dispatch/provider delivery still pending.
- IMP08/IMP12: approved server catalogue, required contacts, schedule/quote checks, fixed merchant intent and overlap protection; default notice/horizon carried from003. Staff close/reopen operations share the same capacity constraint and retain actor/reason. Website runtime cannot call staff operations. No claim that003 lacked these reference foundations.
- IMP10/IMP11: runtime cannot alter policy/open intake; explicit host/database/user/TLS validation and no environment host/service override; production schema/public site unchanged. Runtime login, API cutover, staff authentication and readiness proof still pending.
- Razorpay adapter adapted from003 with004 receipt prefixes, credential version/account/mode binding, no environment proxy inheritance, secret-free credential representation, conservative ambiguous POST handling, and minimized strictly typed payment observations. Provider behaviours still need actual Sarsa account acceptance.

Evidence:29 Python tests; three rollback-contained PostgreSQL suites; build passed. Sequential competing-claim tests are not simultaneous-session concurrency proof. Full completion still needs API authorization, public pages, background recovery/delivery, hosted secrets, actual provider acceptance, backup/restore and operational verification.


## 28 September — access, available times, signed events and saved-work recovery

New004 modules: access.py, availability.py, receipt_view.py, application.py, rate_limit.py, webhook.py, recovery.py; queries/receipt_snapshot.sql; migrations011–014. Existing models/security/payment_policy/payment_evidence/storage updated narrowly. No003 edits, publication or real provider calls.

- IMP01/IMP06: private receipt projection uses current database time, reports appointment/payment/meeting/mail separately, and does not expose provider checkout data or offer another payment from an expired hold. Confirmed-resolution projection corrected. Customer status remains readable while new intake is closed.
- IMP02: bounded recovery claims use SKIP LOCKED, expiring leases and fenced completion. Unresolved money has no appointment/receipt-age cutoff. Persisted cursors cover all listed payments over repeated calls, including an odd-sized collection. Confirmation retains a follow-up scan so a crash or first captured payment cannot hide later payment entries. Provider faults/absent credential versions retain non-secret error reasons.
- IMP07/IMP08: purpose-separated context credentials, Secure/HttpOnly/SameSite cookies, constant-time receipt validation, no email/phone lookup, normalized UTC request fingerprints, independent committed request counters and per-context admission. Unknown source addresses and limiter failures close access rather than disable protection. Limits remain load-test defaults, not a final capacity claim.
- IMP10/IMP12: real claim-based availability, immutable policy/version agreement, no fictitious empty list on outages, restricted body sizes, exact browser Origin, no-store responses including generic errors, no public documentation/admin/legacy unpaid aliases in the new application. The existing public application is not switched yet.
- Signed provider events verify raw bytes before parsing, validate merchant/mode configuration, reject duplicate JSON keys and conflicting event IDs, and commit minimal reference data before acknowledgement. Receipt-only recovery and signed provider callbacks have separate authorization. Supported subscription: payment.authorized, payment.captured, payment.failed, order.paid and refund.processed; do not subscribe other refund lifecycle events until their dedicated handling exists. A processed-refund event waits for fetched payment refund evidence rather than being marked complete prematurely.
- Canonical merchant MID constraints prevent acc_-prefixed aliases from bypassing identity matching or stranding signed callbacks. This is a004 invariant; re-audit003 normalization before proposing a retrofit rather than claiming a witnessed003 defect.

Proof:56 Python tests plus real development PostgreSQL receipt-query, request-limit and recovery-lease checks using rolled-back synthetic records. Production remains unchanged. Remaining: launch-ready checkout/resume/payment-verification routes, delivery/Google authorization, staff interface and auth, rate-counter cleanup scheduler, host address verification, paid-intake readiness, public frontend/Contact migration, concurrency/load/restore/operational acceptance.


## Google owner isolation and credential boundary

004 adds separate client/agency role scopes with fixed approved emails, and rejects an agency grant containing calendar access. Uses drive.file for app-created booking workbooks instead of all spreadsheets/Drive files. Encrypted refresh grants bind project004, OAuth client, role and Google subject so ciphertext cannot silently move between owners. Official signed identity validation plus nonce/PKCE, exact granted permissions, offline-grant requirement and refreshed identity checks are covered by local tests. No fallback to another client's credentials.

For003 retrospective: inspect its actual scopes and encrypted storage before adapting these changes. Its existing nonce/session checks are useful and must be preserved. Sarsa's two account emails are client-specific, never copied into003. A reconnect without a new offline grant fails while retaining the previous DB connection; it must not attach newly requested permissions to an old unverified refresh token. Durable callback state/session/revision handling and persistence remain pending in004, so this entry does not claim end-to-end connection hardening completed.


### Private Google connection persistence added

004 now separates identity-only sign-in from offline account consent. Nonces and PKCE verifiers are encrypted at rest along with raw OAuth state inside an attempt envelope; lookup/browser/session credentials are purpose-bound HMAC digests. Consume state in a committed short transaction before the external exchange, then recheck session revocation/expiry and attempt expiry at final commit; no Google request while holding database locks. Compare captured connection revision so a late callback cannot overwrite a newer grant. Pin role to verified Google subject, and preserve existing grant on validation/revision failure. Unknown commit gets a check-status message, never a false failure/success assertion.

003 adaptation candidate: its current connection exchange holds a transaction/session lock around provider I/O and preserves an old refresh token if Google omits a new one. Reassess those cases with tests before retrofit. Do not copy004 identities, resource IDs or client policy into003. Local SQL/HTTP proof exists for004; hosted callbacks, log redaction, grant-refresh persistence and simultaneous races remain readiness work.


### Explicit host boundary prepared

004 now has a separate Vercel composition root, no legacy application import side effects, pinned canonical host/database identity, dedicated runtime-login requirement and strict TLS. Missing keys or incorrect environment fail closed with a generic response; receipt/context/risk keys are independently generated. The Vercel-only client-address resolver rejects missing, multiple or malformed platform addresses and never uses fallback browser headers. API/studio routes precede the frontend fallback. These are004 local implementation/test results, not claims about003 defects or hosted acceptance. Before003 retrofit, inspect its own proxy contract, resource identity and intended preview behavior. Dedicated runtime role grants, platform log redaction and actual hosted proof remain pending.


### Runtime database identity verified on004

Created SQL-managed sarsa_booking_web with only inherited booking runtime access, no Neon administrator membership, explicit operational timeouts and no password until owner initialization. Removed runtime migration-history read permission. Real PostgreSQL rollback fixtures prove forbidden schema creation, public-opening/price changes, booking deletion and audit/financial-history rewriting are denied. Pooled runtime host is pinned separately from direct maintenance access. Hosted configuration accepts the normal Neon URI but always enforces server certificate/hostname checks using system trust roots; rejects unrelated connection options. For003, audit actual role flags/memberships and TLS/connection pooling before proposing changes; no003 account/role/code was modified. Actual004 authenticated pooled connection and hosted runtime acceptance remain pending.


### Saved Google credential renewal

004 now serializes renewal with a90-second database lease per account/consent revision, performs Google calls outside database transactions, and returns access only after confirmed encrypted persistence. Older refresh cannot overwrite reconnect; ordinary refresh does not change consent revision. Failure leaves prior grant recoverable where provider permits; uncertain token rotation can still require reconnection. Python fault tests and rollback-only PostgreSQL interleavings passed. Before003 retrofit inspect its actual refresh/persistence approach rather than presume a defect. No003 edits and no live account renewal yet.


### Google delivery, workbook ownership and retry safety implemented on004

- Calendar/Meet uses deterministic project/booking/revision identity, reconciles unknown creation by reading the same event, verifies owner/time/markers and exact Meet URL, separates conference-pending from ready, conditionally removes obsolete events and queues cleanup for late old-revision completion. An ended appointment is not given a newly created late meeting. Future003 review must inspect its actual event and revision contract first.
- Separate OAuth owners actually create the client and agency workbooks; verify Drive ownership and reject shared file IDs across roles. Workbook creation intent is committed once; unknown creation searches its marker and never blindly repeats POST. Unresolvable intent needs operator reconciliation because Sheets creation lacks a general idempotency guarantee.
- Per-owner immutable row allocation plus RAW fixed-range writes prevents ordinary delivery retries from appending duplicates or interpreting names as formulas. Conflicting manually edited rows are not overwritten. Project/record/booking/revision labels preserve demarcation; no birth notes are copied. Explicit9999-record bound and no manual edits to the machine tab; rollover/backup are separate work.
- Google jobs use bounded network operations outside transactions, saved leases and booking-before-job lock order. Worker authorization is separate from customer receipts and staff cookies. Customer receipt projects only the current ready Meet URL after authorization; old/cancelled links are withheld.
- Private setup is own-role only and exposes no grants. Automated provider fault tests, actual-role rollback SQL, and desktop/mobile browser inspection cover this implementation. Live provider acceptance and permanent scheduler remain pending. These are004 improvements and003 review candidates, not evidence of a reproduced003 incident. No003 file/account/resource changed.


### Resend transport and signed observations

004 now pins sender/reply-to, tags each send with project and immutable job identity, rejects mismatched payload binding, uses a committed first-attempt time and a conservative23-hour retry ceiling within Resend's24-hour idempotency window. Distinguishes definite rejection from possible accepted send, never automatically changes channel, and returns only provider acceptance. Signed report receiver rejects duplicate headers/JSON fields, verifies raw body with official Svix, ignores unrelated project mail and persists minimal evidence with hash-conflict detection before acknowledgement. Existing003 also uses Svix; inspect each safeguard before treating it as a missing feature. End-to-end message budgets, durable mail dispatcher, event reconciliation and hosted acceptance remain pending on004; no003 code/account changes.


## Revision5 planning additions — not implemented fixes

- IMP01/IMP06: distinguish partial/full refund and accepted-payment amounts from extra-money cases; source receipt_snapshot.sql currently collapses positive refunds to refunded. Requires cross-layer tests in004 and separate003 audit.
- IMP04/IMP06: committed begin-send, frozen payload hash, early webhook binding, append-only delivery observations and cumulative uncertain-attempt evidence. Avoid reusing one execution-state enum as recipient delivery truth.
- IMP10/IMP11: isolate optional provider configuration failures from financial recovery, provide independent scheduler watchdog, and suppress outbound replay during restore until provider effects are reconciled.
- IMP12: shared-team allowance accounting, durable Contact migration and versioned record-copy history are explicit work; no shared003 worker, secrets or data are introduced.

All are planned requirements with acceptance evidence in revision5 P1–P7/A01–A12. No003 source changes or current live defect claims.


## 29 September — email dispatch and receipt implementation

IMP04/IMP06: implemented frozen message snapshots, immutable first-attempt time, per-job rolling allowance reservation, bounded same-key retry, early-event correlation and append-only recipient observations. No fallback channel; provider acceptance and delivery remain separate. Bounce/complaint evidence suppresses further customer sends. Duplicate provider mapping is constrained and conflicting reports retained for review. Partial refund projection now reports separate accepted-payment amounts; repeated observations do not add money twice.

IMP10: malformed optional mail configuration no longer disables the entire hosted application. Separate email worker credential cannot reuse Google/studio/booking encryption authority. Durable mail SQL passed development-only rollback fixtures under actual website role;020 applied development only. Independent simultaneous-worker and hosted/provider acceptance remain pending. These are004 implementation changes and003 audit candidates, not changes to003 or claims its live system has each issue.


## P2 transfer candidates —29 September2026

- Replace a separate offset database-reading watchdog with external completion storage and a health endpoint that never touches Neon.004 uses per-sweep KV keys and an independent GitHub observer; keep scan/publication liveness distinct from actual obligation completion.003 is unchanged; assess its live schedules and measured usage before any retrofit.
- Respect user monitoring budget through verified public standard-runner eligibility and a fail-closed public-repository guard; never assume a shared100-CU-hour pool or treat code cadence as measured consumption. Private fallback needs a separately approved budget/cadence.
- Wake only after matching provider-event commit; ignore other-project signed Resend events without publishing. Preserve durable jobs when publication times out or queue retention/retries expire.
- Propagate failed payment/event lease completion as retry rather than counting it as saved progress. Test this alongside bounded cross-provider recovery and future retry/lease eligibility.
- Keep exact client account/queue/KV/worker origins and independently scoped Google/email/recovery/wake keys. No secret or customer payload in queue/monitor output. Document hosted proof separately from provisioned empty resources and packaging tests.
- Record GitHub delayed/dropped/inactivity-disabled schedule risk and verify real alert subscriptions; do not disguise it with artificial keep-alive commits.004 operational acceptance remains pending.


## P3 transfer candidates —29 September2026

- Save a verified browser payment reference durably before the provider lookup; a timeout must not lose the payment ID or become a second-order request. The callback signature still does not confirm an appointment.
- Require the private receipt for resume/verification without requiring a still-live context cookie. Keep costly provider checks under the checkout quota and ordinary status strictly read-only.
- Coalesce resume reads with a database cooldown/shared recovery lease; require current unpaid evidence, owned slot and committed lease completion before returning launch details. Full/incomplete payment collections fail closed; extra financial observations remain queued for bounded recovery.
- Retain old merchant/mode/key-version bindings during rotation and reject wrong-account fallback. Isolate optional Google/Studio configuration failures from existing payment/status recovery.
- Preserve email local-part spelling for new requests using an explicit normalization version; retain the old normalization/fingerprint contract for V1 retries.

These changes are implemented/tested in004 locally (database021 development only). They are003 audit/retrofit candidates, not assertions that003 has every listed defect and not permission to edit003.

Additional P3 candidate: derive pending/failed receipt state per payment's latest recorded observation rather than any historical pending observation. Keep captured/refund/exception precedence, and retain queued follow-up when a bounded HTTP batch leaves more financial evidence to inspect.


## P5 customer-page candidates —29 September2026

Audit003 for: capability-only session storage with round-trip verification before checkout; retaining the original request after uncertain responses; refresh through read-only receipt status rather than a new reservation; official SDK data validated against the saved receipt; server-only confirmation; separate factual payment/Meet/email states; bounded visible-page status polling rather than repeated provider recovery; rejected stale availability; fixed interaction bounds during choreography; and no invented availability when the backend is unavailable. These are implemented locally for004, not a claim that003 has each weakness.003 remains unchanged.


## P6 calendar-control candidates —29 September2026

Audit003 for explicit client/agency appointment capabilities; database session recheck under a session lock before calendar mutation; shared schedule exclusion for closures; immutable operation replay with truthful current-state display after an earlier closure is reopened; bounded minimal-data calendar listing; protected reopen that cannot release a customer appointment; retained identical request after uncertain save; explicit India timezone and clearing private UI state on sign-out.004 implementation and development fixture evidence are local/development only.003 has not been edited or assumed deficient.


## P5 Contact foundation candidates —29 September2026

Audit003 for enquiry-specific capability and HMAC code binding (request/email/generation), strict immutable request retries, independently idempotent resend operations, durable wrong-attempt/resend/email quotas, code clearing on expiry/lockout/success, and verified submission committed with unique delivery intentions before returning received. A generic cached verified address must not authorise unrelated submissions. Add minimal receipt projection and a separate delivery-readiness guard so keys alone cannot expose unfinished sending. Restrict intake configuration while permitting a narrow locked read, rather than granting runtime permission to open public intake.

These are004 local/development foundation checks only. Delivery/Sheets/frontend integration and concurrent/hosted proof remain pending;003 is unchanged and no defect in003 is asserted without its own audit.

## P5 Contact delivery/page transfer candidates —29 September2026

Audit003 for encrypted frozen code-mail snapshots with keyed integrity (no low-entropy-code plaintext hash), shared booking/enquiry mail reservations and enquiry subcaps, stable retry identity after uncertain send, cross-kind provider-identity ownership locking, superseded-generation fencing, separate owner-checked Enquiries rows with RAW writes and immutable assigned positions, minimal delivery status distinct from saved receipt, and refresh-safe resend operation recovery. Also audit actual rendered visibility, stationary first-click targets and obsolete endpoint closure after callers migrate.

Implemented and checked locally/development in004; real provider/concurrency acceptance remains pending. These are future003 audit/retrofit candidates, not permission to change003 or evidence it has each listed problem.003 source/accounts/records were not modified.

## 29 September — private staff inbox transfer candidate

004 adds role-limited issue projections, detailed verified enquiries only for practice staff,50-row cursor paging, append-only actor/revision/operation-bound review notes and identical interrupted-save recovery. Notes do not mark financial or delivery issues resolved. Deferred feature listeners initialize before sign-in status publication. Later delivery supersedes a generic earlier mail failure, while bounce/complaint/suppression remain visible. Evidence: migration025; tests/test_studio_inbox.py; tests/studio_inbox_database.sql; tests/studio-inbox-browser.js;223 backend tests, actual development rollback checks and desktop/mobile browser proof. Shared robustness candidates; re-audit003 before retrofit. No003 files or accounts changed. Hosted acceptance and the rest of P6 remain pending.

## Owner clarification — Project003 policy and dashboard baseline,29 September2026

Owner confirms Sarsa must inherit Project003 cancellation/refund/rescheduling rules and dashboard behaviour, with implementation defects corrected and transferable improvements recorded for a later003 retrofit. This supersedes the earlier request for a fresh set of Madhuri-specific commercial rules: that general question is no longer a blocker. Inspect reference policy and actual behaviour together; do not copy source defects or003 accounts/contact details.

Reference inspection:003 AstroConnect/src/Component/LegalPage.jsx refund section specifies full refund for cancellations at least24hours before consultation; free rescheduling at least12hours before; under12hours a one-time complimentary reschedule within14days instead of cash refund; completed consultations and delivered Prashna answers non-refundable; approved refunds to original payment source with stated5–7business-day expectation. Contact.jsx says cancellations/refunds are staff handled and cancellation does not automatically refund. src/backend/storage.py cancel accepts only upcoming confirmed bookings, releases capacity, supersedes unfinished confirmations and queues cancellation plus workbook updates; admin.py exposes the protected staff action. StudioAttention.jsx has a manual Razorpay-refund review action. These are inspected local reference facts, not proof of current deployed003 behaviour.

Implementation implications: inherit policy, retain staff review/refund-provider separation, preserve evidence and revised meeting/workbook jobs, strengthen idempotency/revision/concurrency protection. The reference wording does not explicitly settle cash-refund entitlement in the12–24hour window or how repeated rescheduling affects the original notice period; preserve staff review where wording is incomplete rather than inventing automated refund entitlement. Flag any material unresolved commercial decision narrowly only if required for an automated action. Do not treat that gap as a blocker to other work. Privacy/terms final-page authoring remains deferred as requested.

Resend installation/connection is still not confirmed. Owner reports the previous suggested connection was not visible. Rechecked directory: Resend available but not installed, no callable Resend tools. Retried supported suggestion once; no direct authorization URL was returned. Use documented Plugins/Apps installation and authorization route; do not claim a visible link or completed connection. Usage remains private and unverified; public limits already researched.


## 29 September — cancellation strengthening for later003 audit

004 migration026 and studio_appointments.py add client-only DB session revalidation, expected revisions, immutable operation/actor/reason audit and replay-safe cancellation. Calendar cleanup keeps old revision identity; two cancelled workbook snapshots are immutable new revisions. In-flight provider evidence survives. Corrected repeated original capture after cancellation being treated as a different payment; actual second payment still flags review. Browser acknowledgement and identical lost-response retry protect staff actions. Evidence:227 backend tests, restricted-role development rollback fixture including late Google completion, desktop/mobile browser checks. These are local/development proofs only.003 remains unchanged; audit its current implementation before separately authorized retrofit.

## 29 September — staff rescheduling and support improvements for later003 audit

Implemented in004 only, migrations027–029:

- Revision-checked, operation-bound rescheduling preserves original payment/service, rejects occupied slots atomically, retains the one-time late-reschedule deadline, and replaces delivery revisions without recreating obsolete meetings.
- Exact-reference client-only lookup excludes receipt credentials and raw payment payloads. Work retries preserve original identity, uncertainty, first-attempt time and provider idempotency window; they cannot reset the23-hour mail safety cutoff or claim delivery success.
- Refund review requires immutable full-amount evidence under the correct merchant, mode, order and payment. Partial/missing evidence is rejected; cancellation and actual refunds remain separate.
- Contact corrections and lost-receipt recovery require the owner-approved original-phone callback and payment-detail check, recorded as staff attestation. Contact changes refresh affected delivery revisions while retaining appointment, price and payment.
- Assisted recovery uses an eight-digit,15-minute single-use code, five-attempt limit, three-issue/hour limit, supersession and old receipt revocation. Database stores only keyed code digests. Browser stages a new credential before redemption and reconciles uncertain responses before retrying; another booking's receipt is not overwritten.
- Contact activation requires explicit delivery readiness plus protected dependencies and an independent intake gate; missing pieces fail closed.

Proof:238 Python tests,16 frontend protocol tests, build, development rollback fixtures and desktop/mobile browser fixtures. Independent concurrency and hosted acceptance remain pending. Audit003 before separately authorized retrofit; these are not assertions that003 has each defect. No003 code or accounts changed. Earlier Resend failures are historical; authenticated reads succeeded this turn.


### Completion integration: payment-independent browsing and durable rejection (29 September)

004 migration030 separates browsing from merchant readiness, checks the exact server-owned merchant/mode/key-version under the reservation lock, and only returns safe-to-clear missing-payment errors after durable rejection. Existing commitments replay before current configuration checks. Browser script loading follows saved checkout, uncertain receipts survive refresh, and known rejection preserves entered details/valid time. Port only after003 state/role comparison and regression proof; do not copy004 identifiers or migration numbering. Verified with rollback SQL and browser synthetic cases; not yet production-proven.

### 30 September — certificate trust and proven encrypted backup candidates

004's actual backup setup exposed two portability defects: bundled libpq's default system trust path was unavailable, and the slim PostgreSQL container did not contain the expected certificate bundle. Fixed backup access by selecting the runner's installed bundle explicitly and mounting only that public certificate file read-only into the dump container; verify-full and required channel binding remain enabled. The website composition now selects the explicitly pinned certifi bundle instead of relying on libpq's compiled default. Its real pooled endpoint certificate/hostname verification and all 241 synthetic backend tests pass; this website fix remains local until the coordinated website release.

004 backups now use a dedicated schema-only read role, independent owner-held recovery key, Sarsa-owned drive.file grant, streaming authenticated encryption, isolated restoration before upload, stored-byte authentication, same-day duplicate prevention and bounded private diagnostic capture. First hosted export/upload/readback/restore and same-day archive verification passed with 19 production migrations; actual failed-run GitHub emails reached the agency inbox. All 28 backup tests pass. Later audit003 for the same trust-path dependency, narrow access, key custody, account isolation, real restore/idempotence evidence and failure notifications. Do not copy004's host, role, Drive owner, keys or migration numbering. No003 code/resources were changed, and its backup design/defects are not inferred without inspection.


## 30 September additions for later003 review

- Protected local payment handoff: merchant/live/version-bound exact JSON, separate random webhook signing secret, hidden local inputs, Windows encrypted atomic/no-overwrite copy and password-manager recovery ownership. No secret values in chat, command arguments, source or diagnostics. Verify003's own merchant/resources before adapting; do not copy004 keys.
- Private configuration diagnostics: canonical host plus dedicated Recovery authority, fixed boolean format/composition allowlist and explicit no-provider-acceptance label; no database/customer data or secret echo. This resolves invalid optional settings without exposing or rotating them.
- Private Worker handoff: exact existing account/queue/KV verification, original distinct key copies, bounded no-redirect scheduling snapshot before configuration, input-pipe upload and null-device log sink. No duplicate resources or003 changes in this workstream.
- Hosting acceptance: verify actual public HTML, backend JSON and staff/help addresses independently. Vercel cleanUrls normalizes Python index functions; use the actual deployed function address and preserve the request path in rewrites. A frontend200 or successful build alone is not booking acceptance.


###30September2026 — native edge acceptance and safe recovery diagnostics

004’s Cloudflare Worker now uses supported manual redirects and rejects all non200 responses before any redirect, preserving credential non-forwarding. Node tests alone missed the native runtime’s rejection of redirect:error. Added status-only/unknown-error redaction, failed-heartbeat retention and redirect regression checks; native200/302 fixtures and actual scheduled/queue/health acceptance pass. Future003 review should inspect its real edge request options and execution evidence before copying this fix; no003 defect or change is claimed. Unknown provider text never enters recovery logs. Both004 record-copy owners are now verified separately. Conservative004 mail sublimits do not claim to coordinate the shared003 provider allowance; review cross-project capacity separately during the authorised later retrofit.
