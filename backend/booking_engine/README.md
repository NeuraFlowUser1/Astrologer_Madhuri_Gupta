# Permanent Sarsa booking engine

Implementation in progress,29 September2026. These are final implementation modules, not a mock backend. They are not yet routed from the public site. Do not enable paid intake from this foundation alone.

Current website integration and development migration030 evidence are in [verification.md](../../design-review/2026-09-17/15-automatic-booking-plan/verification.md#website-integration-checkpoint--29-september-2026). Historical numbered implementation notes below are not current production-state claims.

## Implemented and checked

- Strict booking input: mandatory email and international mobile, no booking OTP, no price/duration override fields. Birth fields remain service-dependent and are not guessed mandatory.
- Purpose-bound receipt digests and deterministic normalized-request fingerprints.
- Conservative customer actions: reservation expiry, no observed payment or a failed individual attempt never automatically permits another checkout after order creation.
- Versioned, checksum-tracked SQL: bookings, contexts/admissions, variable-length interval exclusion, payment evidence/cases, distinct notification-event identity and signed-provider inbox storage.
- Database lifecycle functions use context -> schedule -> booking/order lock order. The separate global expiry function does not touch context pointers. Only one caller can change an unattempted order to creating. The caller commits before contacting Razorpay.
- Runtime privilege group has no login; it cannot change schemas/migration history or delete records. Financial observations and accepted-payment mappings are append-only for this group.

- Versioned approved catalogue and Monday–Saturday IST schedule; stale quotes and unavailable times rejected inside reservation transaction.
- Committed admissions and atomic reservation/order intent; unresolved checkout guard remains independent of slot expiry.
- Audited staff closures share capacity constraints; only maintenance authority can execute these until staff authentication is connected.
- Merchant/mode/version-bound Razorpay transport, one durable order attempt, minimized payment evidence and canonical database finalization. Additional/late/refunded payments retain independent review records. Acknowledgement/calendar/Sheets jobs are saved atomically. Google and mail dispatch are implemented and locally tested; permanent scheduling and live acceptance remain pending.

- Secure HTTP factory for policy/availability/context/private receipt status and signed payment events; exact Origin and bounded JSON, no public email lookup and no-store responses. Application is not mounted on the public site.
- Database-backed pseudonymous request limits, bounded recovery consumers, expiring leases, pinned credentials and persisted scan cursors. Runtime cannot normalize away uncertain money; provider failures remain saved work.

## Verification

Run from the004 root with dependencies installed:

```sh
python -m unittest discover -s backend/booking_engine/tests -v
npm run build --prefix frontend
```

`tests/database_constraints.sql`, `tests/reservation_database.sql` and `tests/calendar_database.sql` exercise actual PostgreSQL constraints and lifecycle functions using synthetic rows, rolled back in a subtransaction. Execute only on the named Sarsa development branch. It is not a substitute for simultaneous-session concurrency tests.

Migrations run explicitly through `python -m backend.booking_engine.migrate`. Supply `SARSA_MIGRATION_DATABASE_URL` and exact `SARSA_MIGRATION_EXPECTED_HOST` through protected environment settings. Use a direct TLS maintenance connection; never the pooled or website role. Migration failure messages omit database credentials. Applied migration files are immutable; use a new numbered migration for changes.

## Remaining integration

Hosted acceptance for implemented checkout/resume/verification, Contact delivery, staff operations, email dispatch and the permanent worker; cleanup, isolated concurrent/load tests, backups and end-to-end acceptance. The webhook handler stores only authenticated, minimized references; production event retention and cleanup still need operational configuration. No provider callbacks or outbound sends are active here.

Service prices/durations and Google Meet have now been explicitly approved; this is not approval for an unverified public payment launch. Online intake remains on the legacy public application until an explicitly reviewed cutover; this unconnected package does not fix that deployed application's weaknesses by itself. Project003 remains read-only.


Database constructor requires an explicit expected host and database/user/TLS in its protected connection settings. Runtime SQL cannot open intake or edit business configuration. Staff changes and administrative intake/policy changes must take schedule lock4004002 before row locks; checkout paths take context first, then schedule. No provider network call occurs while holding these locks. The development six-attempt/context/hour bound is not a substitute for the pending outer limiter.

Policy defaults are recorded in permanent-resource-manifest.md. Catalogue snapshots in applied migrations are immutable; a future change needs a new version/migration and matching application policy, never an edit to an applied file.


Additional development DB checks: tests/request_limits_database.sql, and `python -m backend.booking_engine.tests.database_checks --recovery` to render the exact receipt query plus lease/follow-up assertions inside the rollback fixture. Run only on the named isolated development branch.

`create_application` requires protected signing keys and an explicit trusted client-address resolver supplied by the hosting adapter. Do not pass X-Forwarded-For through unchecked. No environment defaults, public activation flag bypass or mock account is provided. Paid routes are not registered until their full readiness/dispatch integration is complete.

Configure only these Razorpay events when the dedicated account exists: payment.authorized, payment.captured, payment.failed, order.paid, refund.processed. Webhook secrets are mode/account-scoped; maintain the previous secret while older deliveries can retry. Database MIDs use the canonical alphanumeric identifier without acc_. Recovery accepts configured original credential versions and never substitutes another client/account.


Google integration foundation: google_oauth.py validates the two approved owners, requests role-specific permissions, verifies signed Google identity, refreshes tokens with an account recheck, and encrypts role/client/subject-bound grants. It is the internal provider boundary used by the optional private studio routes described below. See permanent-resource-manifest.md and verification.md for the remaining hosted setup and operational requirements. Protected settings are SARSA_GOOGLE_CLIENT_ID, SARSA_GOOGLE_CLIENT_SECRET and SARSA_PUBLIC_ORIGIN; no implicit .env loading or another client's default credentials.


Private setup is now implemented by studio.py, studio_assets and migration015. Optional StudioServices mounts /studio, identity-only /api/studio/sign-in/start and callback, own-role /api/studio/google/start and callback, status and logout. Customer intake is independent. Local production Vercel entrypoint/routing is wired in api/index.py and vercel.json; actual deployment/packaging/runtime proof is pending. GoogleOAuth remains the bounded provider layer; StudioServices owns durable attempt consumption and session/revision checks around it. See the manifest for protected settings and pre-hosting conditions.


Google Calendar/Meet and per-owner Sheets delivery are now implemented by google_workspace.py, google_records.py and google_delivery.py with migrations018–019. The private studio can prepare and link each owner's workbook. The internal one-job endpoint /api/internal/google/run requires a separate SARSA_GOOGLE_WORKER_KEY and has no browser/customer authority. It is not a deployed scheduler. Missing this optional key leaves private setup available and worker calls closed. Configure it only as a protected Production setting and the dedicated permanent worker's secret, never a frontend variable or another client's secret.

Verification: `python -m backend.booking_engine.tests.database_checks --google` renders payment-to-Calendar/Sheets recovery assertions with the actual receipt query; `--workbooks` renders once-only workbook intent, ownership separation and exact private-status query checks. Execute development-only inside rollback transactions using runtime authority; the workbook fixture expects the website role already selected. See permanent-resource-manifest.md for exact evidence, provider limitations, row capacity and pending hosted setup. No live provider resources or messages have been created by these tests.


Resend boundary: resend_email.ResendSender reads SARSA_RESEND_API_KEY when explicitly constructed. It accepts only an immutable prepared message with the fixed Sarsa sender/reply-to and matching project/job tags, plus a committed first-attempt timestamp. email_delivery.py invokes it only after committed database begin-send permission; the protected email worker key and approved nonzero budget are additionally required. /api/webhooks/resend is mounted with optional SARSA_RESEND_WEBHOOK_SECRET; without that separate signing secret it returns503. Official Svix checks raw bytes, then minimizes and deduplicates reports in provider_inbox. Migration020 reconciles saved job/provider identity and projects delivery observations independently from execution state; reception alone does not set customer delivery state. Owner reports the webhook was registered and its signing secret saved before deployment. Hosted receiving acceptance remains pending; preserve Project003's webhook and keep Sarsa sending inactive until verification. Test SQL renderer: `python -m backend.booking_engine.tests.database_checks --email-events`, development rollback transaction only.


Email dispatch (29 September): migration020 is applied on development only; production still019. Apply the reviewed migration before deploying the new receipt query. Email policy defaults to zero allowance and SARSA_EMAIL_WORKER_KEY is unset. Routes /api/internal/email/run and /api/internal/email/events require the separate email-only bearer key and reject caller-provided job/destination fields. Do not reuse Google worker or studio keys. No permanent scheduler exists yet. Run `python -m backend.booking_engine.tests.email_database_check` to render rollback-only development checks; these are sequential transaction tests, not concurrent-session proof. Broader/live verification remains in the manifest.


## Recovery scheduler integration —29 September2026

`recovery_worker.py` exposes authenticated empty-body planning/payment recovery lanes; `queries/recovery_plan.sql` returns only lane delays and attention. `wake.py` publishes a bounded best-effort empty hint after committed matching webhook events to the fixed Sarsa Cloudflare worker. Queue failure leaves durable work available for15-minute rescue. This scheduler slice needed no new schema migration; its query depends on020. Payment HTTP composition is now implemented as described below; Contact integration remains pending. Absent payment adapters fail closed. Payment recovery completion reports retry if its lease was lost.

## Payment HTTP implementation —29 September

`checkout.py` registers POST `/api/checkout` and `/api/checkout/resume`; `checkout_verification.py` registers POST `/api/checkout/verify-payment`. All require exact Origin and the durable checkout quota (30/hour per scoped address); status keeps its separate read quota. New reservation additionally requires the secure context cookie. Resume and verification require `X-Booking-Receipt` plus `request_id`, independently of that cookie. Neither email nor mobile grants receipt access.

New reservations use `BookingRequest`, default normalization_version2: preserve email local-part spelling, normalize its domain through EmailStr, and include version2 in the fingerprint. Explicit version1 reproduces the legacy lowercase-email fingerprint without adding a version field to that hash. `BookingInput` remains the original internal V1 model. Phone remains mandatory/validated, and neither version adds an OTP or accepts a client price.

Resume never creates an order. Migration021 adds a database-backed15-second resume cooldown, sharing the90-second payment recovery lease. One call checks the pinned order and bounded payment collection; a full100-item page fails closed. Up to two financially relevant observations go through the existing finalizer; larger sets retain a recovery cursor. Only a fresh unpaid result, saved lease completion and current slot ownership return a minimal `checkout` object (public key ID, saved order ID, price and currency). No database transaction stays open during provider calls. Lost lease/claim, unknown creation, pending/captured money or provider faults return no launch. Existing reservations remain recoverable when new intake is closed; this is not a global provider-order cancellation switch.

Receipt `check_payment` means call resume to check readiness, not permission to open Razorpay. `resume_payment` appears only with a fresh checkout payload from that request. Never cache that payload for later reuse; get fresh readiness when reopening. Ordinary status polling never calls Razorpay. No expired attempted order authorizes a new checkout merely because its payment collection is empty.

Verification checks the signature against the stored order ID and original credential version. It commits a minimal `checkout-verify:<payment_id>` inbox reference before fetching payment facts, so a crash/provider timeout cannot lose the callback's payment reference. Only the existing payment finalizer determines confirmation/review/refund outcomes.202 `verification=pending` means confirmation is still being checked; it does not mean payment failed. Receipt output excludes internal booking/context/merchant identities and secrets.

Protected production settings (not frontend variables): `SARSA_RAZORPAY_ACCOUNTS` is one JSON object with exactly merchant_id, mode (`live`), current_version and versions. Each of1–8 retained version objects has exactly version, key_id and key_secret. `SARSA_RAZORPAY_WEBHOOK` has exactly merchant_id, mode (`live`) and signing_secrets (one or two during rotation), bound to the same configured account. Old orders require their pinned version; never replace it with the current key silently. Missing/invalid settings close payment operations while preserving receipt/owner access. Invalid optional Google/Studio configuration likewise closes only its own routes; it cannot disable valid payment recovery. No secrets have been generated, requested in chat or configured by this code change.

Development now has021; production remains019. Apply reviewed020 and021 before deploying this backend.174 synthetic Python tests pass, actual website-role development rollback checks pass, frontend build and compile pass. No real merchant test, hosted payment acceptance, concurrent-session proof or public opening is claimed. See the execution plan for remaining readiness, operations, customer-page integration and live acceptance work.

See `workers/booking-recovery/README.md` from the client root for the permanent Worker, real queue/KV identities, four protected-key names, independent non-Neon GitHub monitoring, deployment order and proof boundaries. Worker and monitor are not live yet. Public intake/email budget remain closed/zero. No local loop, customer-controlled destination or reuse of003 runtime/resources.


Private calendar controls (29 September): `studio_calendar.py` and migration022 add client-only POST `/api/studio/calendar/list`, `/close`, `/reopen` through the existing Studio. No agency booking authority, public calendar mutation or commercial cancellation/refund/reschedule rule is added. All mutations recheck and lock the signed session, acquire the common schedule lock, and use the existing immutable action journal. List returns at most50 active claims with a UUID continuation; no email/phone/payment/receipt fields. Raw owner closure functions remain ungranted. Production needs reviewed migrations020–022 before hosting the new code; development has022. Test source `tests/studio_calendar_database.sql` must run inside a rollback-only development transaction with temporary runtime-role assumption, never production. `tests/studio_calendar_browser.mjs` intercepts private API requests for isolated visual QA only.


Contact foundation (29 September): migration023 is applied to development only. POST /api/contact/start, /status, /resend and /verify use X-Enquiry-Receipt, strict schemas, exact Origin and committed quotas. Contact verification is independent of OTP-free booking. Optional phone is validated when present. A valid start saves a challenge, not a received enquiry; only atomic code verification can return received. Code expiry/lockout/success clears live ciphertext and suppresses obsolete delivery intentions. Receipt status returns no customer content or secret.

Protected SARSA_CONTACT_KEYS is JSON containing digest (canonical32-byte URL-safe base64 key) and encryption (1–3 ordered canonical Fernet keys). Never use a frontend/VITE setting or reuse booking/Google/worker keys. It is NOT configured by this implementation. Ciphertext rotation retains old encryption keys until encrypted delivery retries have drained/expired (up to23hours), not only code windows. Digest rotation requires closed intake and resolution/expiry of challenges, receipts and encrypted message retries. No plaintext-code logging or response projection.

The production composition leaves contact_delivery_ready=false; both application readiness and the owner-controlled contact_intake.public_open flag must eventually permit new challenges. Local code-mail/shared-budget/event consumers, enquiry Sheets copies, immediate scheduling/cleanup and the approved React caller are integrated and checked. Keep intake closed until hosted acceptance and owner setup. Obsolete routes are now guarded410 in both entrypoints; no real Contact delivery occurred. Run tests/contact_database.sql only inside an enclosing rollback-only development transaction; it deliberately manipulates synthetic expiry and temporarily opens the switch within that transaction.


Latest Contact integration: development through024 (production last recorded019; recheck before deployment). contact_delivery/contact_records/contact_messages and private Contact worker routes implement encrypted mail retries and separate owner-checked Enquiries tabs. All booking/enquiry mail uses one reservation ledger plus Contact subcaps. Seven-lane recovery includes code expiry and Contact jobs. The actual React Contact page uses /api/contact/{start,status,resend,verify}; no generic OTP modal/Render fallback. Retired public paths return410. See canonical contact-integration.md for protocol, rotation, scopes and evidence.218 Python/21 worker/6 Contact protocol tests and Contact/booking browser fixtures pass; no real provider/public acceptance implied. All mail caps0 and Contact composition/intake remain closed.

## Private staff inbox — 29 September checkpoint

Requires migration025 (applied to development only). POST /api/studio/inbox/list, /detail and /review recheck exact browser origin, session audience and role in both HTTP and database layers. Database helpers are not runtime-executable; raw staff_reviews writes are denied. Notes do not change provider state. Tests: test_studio_inbox.py, rollback-only studio_inbox_database.sql, and isolated studio-inbox-browser.js. Browser fixture expects the actual Studio static assets on127.0.0.1:3016 and intercepts all dynamic API calls. Development is025; production last recorded019 is historical and must be rechecked before deployment. See the current execution plan for full remaining scope.

## Staff cancellation —29 September

Development now requires/applies026_staff_cancellation.sql. POST /api/studio/appointments/detail and /cancel use client-only session/Origin/quota validation. Cancel requires claim UUID, operation UUID, expected revision and reason; money is unchanged. Frozen old meeting cleanup and new cancellation/record jobs commit together. staff_cancellation_database.sql must run only in a development rollback transaction. staff-cancellation-browser.js expects an isolated static Studio preview on3017 and intercepts dynamic requests. Protected-setting helper now supports SARSA_CONTACT_KEYS; -VerifyOnly performs no handoff. See canonical plan stock check for remaining rescheduling, provider and operational acceptance.

## Current staff/support contracts — development029,29 September2026

Supersedes historical025/026 status above. Production remains019 and closed. Applied migrations are immutable.

-027_staff_reschedule.sql: client-only rescheduling, audit/revision/idempotency checks, atomic capacity change and obsolete Google-work suppression.
-028_staff_support.sql: exact booking lookup, eligible work retry and evidence-based full-refund review; no money movement.
-029_staff_receipt_recovery.sql: callback-attested contact correction and receipt replacement, expiring/attempt-limited grants, stale access revocation and interrupted-response reconciliation.

POST /api/checkout/recover-receipt pairs with /booking-help; protected staff support is in /studio. New receipt credentials are staged only in sessionStorage, never URLs/emails. Inaccessible original phone means manual support; the staff checkbox records human attestation, not independent call verification.

Development rollback fixtures: staff_reschedule_database.sql, staff_support_database.sql, staff_recovery_database.sql. Browser fixtures intercept synthetic API responses: cancellation/rescheduling/inbox/support on3017, contact/recovery on3018. Current checks:238 Python tests,16 frontend protocol tests and build pass. Hosted and concurrent acceptance remain pending.

Contact delivery also requires SARSA_CONTACT_DELIVERY_ENABLED=true, all dependencies and the separate database intake gate. Keep closed until hosted proof and shared email allocation are complete. See canonical manifest for provider handoff.
