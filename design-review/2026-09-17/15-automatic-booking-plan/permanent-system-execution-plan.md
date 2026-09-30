# Permanent Sarsa booking system — revision 5 implementation plan

## Whole-website completion plan — current execution authority

Read [website-completion-implementation-plan.md](website-completion-implementation-plan.md) for the current integration/release sequence, revision2 implementation contracts in section13, and the owner clarification: remove temporary incomplete-setup restrictions, retain permanent correctness/security protections, and complete all non-payment work while Razorpay is deferred. The existing detailed booking contracts and dated evidence below remain valid where not explicitly superseded. This is a reviewed plan, not a claim of implementation or deployment.

## Current checkpoint — 29 September 2026, development migration 029

This checkpoint supersedes earlier status summaries below; those entries are historical evidence.

**Implemented and checked:** staff rescheduling, private exact-reference booking lookup, safe retries of eligible saved work, review of provider-verified full refunds, verified contact corrections and assisted receipt recovery. Cancellation remains separate from refunds. Staff must first call the mobile number already saved on the booking and verify payment details. The owner explicitly approved this procedure; an inaccessible original number requires manual review. The system records staff confirmation; it cannot prove that a phone call occurred.

Development has migrations001–029. Production was rechecked at019_google_delivery.sql with zero bookings and public booking closed; it was not changed. Development checks finished with zero bookings, delivery jobs, enquiries, support reviews, sessions and recovery grants; both intake switches are closed, daily email allocation is zero, and temporary maintenance role membership is absent. No real message, refund or payment was sent, and no new source was published.

**Resend now works.** Authenticated reads succeeded: daily sending0/100, monthly94/3000, three domains out of three allowed. Sarsa's mail subdomain and enabled seven-event webhook are verified; Project003's separate domain/webhook are retained. These are shared-account usage snapshots, not a reserved Sarsa allocation. Earlier connector-failure entries below are superseded. No further installation is needed from the owner.

**Evidence:**238 Python tests and16 frontend protocol tests pass; frontend production build passes with an existing large-bundle advisory. Restricted-role SQL rollback fixtures cover rescheduling, support retries/refund evidence and assisted recovery. Browser fixtures cover cancellation, rescheduling, inbox/support, contact correction and receipt recovery at1440/390/320 widths, interrupted responses, identical retries, agency restrictions and no horizontal overflow. Relevant screenshots were inspected and copied into qa/2026-09-29-*.png. These are development and isolated-browser proofs, not independent concurrent-session, real-provider or production acceptance.

**Still required before opening:** dedicated Sarsa Razorpay merchant creation/activation; manual Sarsa Vercel protected-setting handoff; reviewed production migrations020–029 and deployment with intake closed; Google owner sign-in and separately owned workbook/Meet proof; dedicated worker and independent monitor deployment; bounded shared email allocations and real delivery/callback proof; concurrency, backup/restore and operational failure acceptance. Privacy/terms final authoring stays last as requested. No paid upgrade or new backup destination is assumed. Neon currently reports six hours of recovery history; the owner has been asked whether to retain free service and plan a separate encrypted daily backup.

Contact delivery has a closed activation gate: SARSA_CONTACT_DELIVERY_ENABLED must equal the exact string true, all required contact/staff/email/webhook/recovery/wake settings must exist, and the independent database intake switch must permit requests. This flag has not been enabled. Hosted acceptance and sending allocations come before activation.

## 29 September — stock check and staff cancellation implementation

Checked current dirty client source, canonical plan/manifest, applied migration chain and Project003 reference policy/dashboard code before continuing. No general permission checkpoint is needed. Latest independent implementation: client-only appointment detail/cancel routes and Studio controls; migration026. Cancellation journals actor/reason/operation/revision/notice, atomically frees capacity and queues two cancellation emails, old-revision Google cleanup and two new-revision workbook records. It does not alter accepted money/refund evidence. Original attempted payloads and in-flight completion leases survive. Repeated same accepted captured evidence after cancellation no longer generates a false additional-payment incident; truly different payments still do. Exact operation retry is safe; stale revisions/agency/wrong-origin access reject. UI requires acknowledgement, locks calendar changes after an uncertain reply, clears private data on role loss, and explicitly distinguishes cancellation from refund. Screenshot review caught and corrected a stale “confirmed” summary after success.

Proof:227 synthetic backend tests; frontend production compilation; Python compilation; targeted JS lint; actual website-role SQL rollback fixture before and after development migration; isolated browser1440/390/320, required acknowledgement, identical interrupted retry, agency denial, no overflow, screenshots visually inspected. SQL fixture includes late Google create completion/cleanup, capacity release, unchanged accepted payment, same-payment replay and genuine additional-payment review. Migration026 SHA2568643ebe86485785d6553ec072d773e262d18df733d822bf86b0a4bf604daa2c0 applied only to development under001–025 checksum guard and migration lock. Fixture data rolled back; no provider calls, emails, refunds, production changes or publication. See staff-appointment-changes.md and tests/staff_cancellation_database.sql. Independent concurrent-session proof remains pending.

Stock check also found the protected-setting helper lacked SARSA_CONTACT_KEYS. It now generates the parser's exact digest/encryption-array shape with separate random keys. Windows PowerShell -VerifyOnly passes without clipboard/file/account changes. No actual protected setting was generated or copied. Owner must use the actual Copy mode only during the manual Vercel handoff.

Resend retry after owner reported CLI authorization: usage first returned authentication accepted/retry, then USER_NOT_LOGGED_IN; domain request returned another authentication-retry message. Tools are exposed, but no account data/usage or domain verification was obtained. Do not ask owner to recreate domains or keys, do not claim usable access, and do not let this block independent implementation. This is a connector authorization failure visible in this session, not evidence of an incorrect Resend account.

### Historical inventory before migrations027–029

| Area | Current verified state | Still required |
| --- | --- | --- |
| Permanent source/database | New booking engine and development001–026; live production last recorded019 is historical | Recheck production ledger; reviewed deployment/migrations with intake closed |
| Booking and Contact customer experience | Actual React integration and local failure-path checks; no booking email OTP; both booking contact fields required | Hosted end-to-end proof, final activation readiness, provider credentials |
| Staff operations | Google connections/workbook preparation, calendar blocks, enquiry/problem inbox and cancellation implemented locally | Rescheduling, contact correction, receipt recovery and complete finance/support workflow |
| Recovery/monitor | Dedicated queue/KV provisioned; worker and independent public-repository monitor prepared | Protected secrets, actual worker/monitor deployment, failure-alert receipt, quota/CPU evidence |
| Google | Owner accounts and OAuth project selected; protected baseline settings owner-reported saved | Actual sign-in, separate ownership, workbook and Meet acceptance |
| Resend | Public free limits researched; tools exposed; authenticated read still failing | Working connector access, measured shared usage/allocation, real send/callback acceptance |
| Razorpay | Merchant identity/adapter boundaries implemented; dedicated account pending creation | Owner partner-account creation/activation, exact merchant protected settings, controlled payment proof |
| Operational acceptance | Extensive synthetic/local and rollback checks | Independent concurrency, backup/restore, retention/keys/operator acceptance and controlled hosted failure proofs |
| Final public release | No new source publication or live intake activation in this pass | Privacy/terms last per owner; complete acceptance and concrete cutover decision |

Rescheduling is a separate atomic move, not cancel-and-rebook. Preserve the original claim if the new interval is unavailable; keep original and replacement meeting identities until cleanup completes. The approved003 policy remains authoritative; no repeated general policy questionnaire is required. This inventory is not a claim that all independent work is complete or that the whole programme is ready.


## Owner clarification — Project003 policy and dashboard baseline,29 September2026

Owner confirms Sarsa must inherit Project003 cancellation/refund/rescheduling rules and dashboard behaviour, with implementation defects corrected and transferable improvements recorded for a later003 retrofit. This supersedes the earlier request for a fresh set of Madhuri-specific commercial rules: that general question is no longer a blocker. Inspect reference policy and actual behaviour together; do not copy source defects or003 accounts/contact details.

Reference inspection:003 AstroConnect/src/Component/LegalPage.jsx refund section specifies full refund for cancellations at least24hours before consultation; free rescheduling at least12hours before; under12hours a one-time complimentary reschedule within14days instead of cash refund; completed consultations and delivered Prashna answers non-refundable; approved refunds to original payment source with stated5–7business-day expectation. Contact.jsx says cancellations/refunds are staff handled and cancellation does not automatically refund. src/backend/storage.py cancel accepts only upcoming confirmed bookings, releases capacity, supersedes unfinished confirmations and queues cancellation plus workbook updates; admin.py exposes the protected staff action. StudioAttention.jsx has a manual Razorpay-refund review action. These are inspected local reference facts, not proof of current deployed003 behaviour.

Implementation implications: inherit policy, retain staff review/refund-provider separation, preserve evidence and revised meeting/workbook jobs, strengthen idempotency/revision/concurrency protection. The reference wording does not explicitly settle cash-refund entitlement in the12–24hour window or how repeated rescheduling affects the original notice period; preserve staff review where wording is incomplete rather than inventing automated refund entitlement. Flag any material unresolved commercial decision narrowly only if required for an automated action. Do not treat that gap as a blocker to other work. Privacy/terms final-page authoring remains deferred as requested.

Resend installation/connection is still not confirmed. Owner reports the previous suggested connection was not visible. Rechecked directory: Resend available but not installed, no callable Resend tools. Retried supported suggestion once; no direct authorization URL was returned. Use documented Plugins/Apps installation and authorization route; do not claim a visible link or completed connection. Usage remains private and unverified; public limits already researched.


## 29 September — private staff inbox and provider-quota correction

Implemented the scoped private inbox in migration025, studio_inbox.py, storage.py and studio_assets/inbox.js, reusing /studio. Practice staff can read verified enquiries and recorded payment/delivery issues. NeuraFlow can read only its own technical record-copy issues; list projections omit customer contact details. Review notes are append-only, actor-bound, revision-checked and replay-safe; recording a note never resolves a provider fact or changes money, bookings or delivery. Lists are bounded to50 with stable cursor paging; details show the latest20 notes. This is not complete P6: commercial-policy appointment changes, finance resolution, receipt recovery, comprehensive connection/heartbeat/backup health remain outstanding.

Browser inspection found and fixed a fast-status/deferred-script initialization race, and request cancellation now owns its own timeout. Isolated desktop1440/mobile390/320 checks pass for literal rendering of unsafe text, identical retry after a lost save response, agency isolation and clearing on role loss; screenshots visually inspected. This uses synthetic intercepted responses, not hosted acceptance. Backend223 tests and frontend production build pass. Existing large-bundle advisory remains. Real development SQL fixture proves restricted role/session access, pagination, replay/conflict/revision behavior, persistence of underlying issues and failure/delivered/bounce precedence; fixture rolled back. Migration025 applied only to development with001–024 checksum guard and migration lock; SHA25675ed0c91f3874ac41d33eb770734d6de1517c78b1ee41e66097f549781215fbd. Post-apply counts:25 migrations, zero enquiries/bookings/reviews; maintenance role cannot SET website role. Production was not queried or changed.

Official Resend quota documentation checked29 September: Free transactional allowance100/day and3000/month, including inbound and outbound; each To/CC/BCC recipient counts separately. Daily reset is midnight UTC, not rolling24hours. Sarsa's local rolling24h/31day reservation guards are intentionally conservative; they cannot measure or reserve003's share of a common Resend team. Source: https://resend.com/docs/knowledge-base/account-quotas-and-limits . Public limits no longer require an owner lookup. Private current account usage/team identity still requires authenticated access. Available Resend plugin was discovered as not installed/connected and offered to the owner; no Resend tools became available during this pass. No usage figure, nonzero allocation, upgrade or message send is claimed.

Actual pending owner boundaries: Resend connection for private inspection; approved cancellation/refund/rescheduling rules (question sent; no invented commercial defaults); Razorpay creation/activation; protected remaining Contact/worker configuration and manual Sarsa Vercel handoff; owner Google authorization and hosted workbook/meeting/delivery acceptance. Privacy/terms remain the final content task as requested. Continue independent implementation automatically; these are not requests for another general go-ahead.


28 September 2026. Current execution authority for completion of Project004's permanent booking and notification system. Replaces revision3's stale source inventory and execution sequence. Existing C01–C08 in [implementation-contracts.md](implementation-contracts.md) and R4.1–R4.7 in [implementation-detail-review.md](implementation-detail-review.md) remain binding except where this revision explicitly tightens them. [Resource manifest](permanent-resource-manifest.md) owns account/configuration evidence; [verification](verification.md) owns completed checks; [improvement register](004-to-003-improvement-register.md) owns later003 transfer candidates. Do not create a competing status tracker.

The revision5 planning pass changed documentation only; the dated implementation checkpoints below supersede that planning-time state. Local source inspection is current; resource observations retain their recorded dates and owner-reported/agent-verified labels. No new live-account inspection, private-record access, deployment, message, payment, database migration or003 change occurred in this planning pass. Earlier dated entries are history, not current instructions.

## P5 Contact delivery and page checkpoint —29 September2026

Implemented the approved HTML14 composition in the actual React Contact route, connected to final same-origin enquiry contracts. Hero assembly starts on mount; later sections assemble once on entry, with reduced-motion and background-loop controls. Public enquiry readiness remains deliberately disabled pending hosted acceptance. This is completed local/development integration, not a live release or completion of P5/P6/the programme.

Encrypted verification/acknowledgement/practice mail consumers, shared booking/enquiry mail reservations and suppression, signed Contact delivery observations, separate owner-checked Enquiries tabs and seven-lane recovery integration are implemented. Migration024 is applied to development only after rollback fixtures and checksum checks. Contact code mail receives first priority; each queue pass has a90-second total deadline. The15-minute rescue cadence and non-Neon monitor remain unchanged. Slow provider work, queue fairness under sustained load and five-minute code delivery still require hosted timing proof; no delivery-time guarantee.

Legacy generic OTP, unpaid booking aliases and old Contact submissions now return410 in both local application entrypoints. The unused EmailOtpModal/Render fallback was removed; no other client's application or live deployment was changed. Remaining work: independent-session contention/load proof, staff exception/finance handling, reviewed retention, actual owner Google connections/workbooks, protected Contact/worker configuration, Resend capacity allocation, deployment/monitor acceptance, Razorpay creation and real payment testing, then final legal pages/cutover review. See contact-integration.md and the latest verification entry for exact boundaries.

## P5 customer booking checkpoint —29 September2026

The approved HTML16 booking design now backs the actual React booking route and same-origin checkout/status/resume/verification contracts. Email and mobile are required; booking OTP, sample slots, manual payment fields and local confirmation are removed from this page. Server receipts drive payment, appointment, Meet and email facts. This is a local booking-page checkpoint, not completion of P5 or permission to publish/open bookings. Contact migration, staff/finance tools, hosted acceptance and remaining programme checks still apply. See [customer page integration](customer-booking-integration.md) and the latest verification entry. Sarsa's Razorpay account is still pending creation; guide the owner before real payment configuration and testing. Independent engineering work continues.

## P5 Contact foundation checkpoint —29 September2026

Recovered the interrupted Contact component and corrected its database permissions and rate-limit constraint. Migration023 is applied only on development after rollback tests and a checksum guard; public intake remains closed. Purpose-bound code verification, exact-request/resend recovery, bounded attempts/expiry, minimal receipt status and atomic verified-enquiry/follow-up intentions are implemented. A separate composition safeguard prevents new enquiries before delivery is integrated, even with valid keys. See [Contact integration](contact-integration.md) and verification.md.

At this earlier foundation checkpoint, Contact email/Sheets consumers, immediate recovery integration, approved React Contact page and coherent legacy retirement were unfinished; the later delivery/page checkpoint above supersedes this list. Do not deploy/open this component as a complete contact system. The production database and live website were not changed. This checkpoint supersedes earlier next-step wording only for the durable Contact foundation; all delivery, staff, hosted and final-launch work remains.

## P6 private calendar checkpoint —29 September2026

Client-only Studio calendar listing and close/reopen controls are implemented and checked locally. Migration022 passed rollback fixtures under the website role, was applied to development only, and passed the fixture again; production is not changed. Calendar actions share the existing capacity lock/exclusion and action journal. Agency role has no appointment access through these routes. No cancellation/refund/rescheduling rules were invented. Evidence and limitations are in verification.md and [Studio calendar integration](studio-calendar-integration.md).

This completes the calendar-control slice, not P6. At the calendar checkpoint Contact still used the legacy caller; the later P5 Contact checkpoint above records its local replacement. Remaining staff work includes exceptions inbox, policy-approved appointment changes and finance support; hosted/concurrent-session proof remains outstanding. Next independent implementation: durable Contact records, purpose-bound verification and delivery, then connect the accepted contact design to those routes. Razorpay account remains pending; no new owner action was needed for this calendar slice.

## Execution update —29 September2026

The source inventory below records the pre-implementation baseline. P1 now includes durable email dispatch, frozen message snapshots, allowance reservations, signed-event projection and partial-refund receipt correction. Migration020 is applied to development only; production remains019. Evidence:139 Python tests, successful frontend build and rollback SQL checks. Simultaneous-connection, hosted and real-provider acceptance remain outstanding. Apply production020 before deploying backend code that calls its functions.

Cloudflare access is verified for neuraflowindia@gmail.com, account162c1ab1ba0619c1c78d9495f3260f18. Script inventory returned only003's existing worker; no Sarsa worker was created. Billing inspection returned403, leaving subscription/shared allowances unverified.

**P2 decision settled: use15-minute recovery with monitoring that does not independently query Neon.** The owner conditionally selected15minutes if a separate database-reading monitor is unnecessary; that extra database read is not required for independent liveness monitoring. Do not activate the obsolete minute-level polling proposal. The production compute has0.25CU minimum,2CU maximum and default idle suspension. Continuous minimum activity consumes approximately180CU-hours/30days, exceeding Neon's published100CU-hour/project Free allowance before development usage. This is a lower-bound capacity calculation, not a measured bill.

Selected direction: immediate dedicated004 queue wake-ups after committed events, plus15-minute database rescue. Lost immediate signals could add roughly15minutes plus processing time to recovery. This supersedes the earlier3-minute sweep alarm target. Monitor a missing completed sweep after a bounded grace period: initially20minutes since the last verified completion, subject to measured execution and monitor latency; this is an operational threshold, not a guaranteed alert-delivery time. The alternative is not guaranteed free: measure idle overhead, retries, peaks and development usage. Published Cloudflare Free queues include10,000 operations/day,24-hour retention and normally three operations per delivered message; actual shared capacity remains unverified.

Implementation must specify post-commit publication, authenticated bounded empty wake-ups, delayed wake-ups for future due jobs, bounded draining and rescue after failed publish or queue expiry. Database jobs remain authoritative; queue acknowledgement never means appointment/payment/email success. Duplicate wake-ups preserve original job identities. Contact OTP requires immediate processing and its own short deadline, not reliance on rescue. Timing approval is settled; hosted readiness, actual account capacity and protected-key handoff still precede activation. No paid resource purchase is authorised. Independent local work continues.

Sources: [Neon Free allowance](https://neon.com/blog/neon-backend-is-ga), [Cloudflare queue pricing/retention](https://developers.cloudflare.com/queues/platform/pricing/), checked29 September2026. Manifest records actual account evidence.

## P2 implementation checkpoint —29 September2026

The15-minute recovery component is implemented locally in `workers/booking-recovery/` and backend `recovery_worker.py`, `wake.py`, `queries/recovery_plan.sql`. Dedicated Sarsa queue and KV heartbeat resources are provisioned in the verified account. Worker/backend/monitor are not deployed; protected worker keys, hosted acceptance and public activation remain pending. See the component README for exact timing, retry/health semantics, owner handoff and limits. No new schema migration in this slice; development020/production019 remain unchanged.

The scheduled sweep inspects saved obligations and publishes a necessary bounded wake-up; its external heartbeat proves that scan/publication, not success of every provider operation. Queue workers process one job per due lane, respect saved retry/lease times and recheck the durable plan. Website event receivers publish only after a saved event commits; unrelated003 Resend events do not wake004. Upcoming checkout/contact routes still need the same post-commit hook as they are completed. Payment lease completion now propagates false as retry rather than reporting committed progress.

Owner approved GitHub monitoring subject to a100-minute/month ceiling. Live repository metadata confirms NeuraFlowUser1/Astrologer_Madhuri_Gupta is public; standard public jobs do not consume private-plan minutes. Prepared monitor runs08/23/38/53UTC, reads Cloudflare KV health only and has a job-level exact-repository/public-visibility guard before runner allocation. No release/build/push/PR trigger. If visibility becomes private the job skips; do not enable a billed fallback. No workflow has been published or run. GitHub can delay/drop schedules and disable public schedules after60days of repository inactivity; operator ownership, failure-notification delivery and ongoing enablement must be verified, not assumed. No fake keep-alive commits.

Local evidence:150 Python tests,19 worker/monitor tests, restricted website-role development rollback query checks, frontend build, workflow YAML/security-budget checks, Windows helper check-only and Wrangler packaging dry-run. Still outstanding: independent-session contention/peak CPU/drain proof, exact provider acceptance, cleanup under approved retention, complete operational metrics/staff handling, credential handoff, deployed worker/monitor and controlled alert test. This checkpoint does not mark full P2/P3–P7 complete.

## 1. Objective, boundaries and definition of success

### P3 HTTP implementation checkpoint —29 September2026

Checkout/resume/verify routes and pinned production payment configuration are now implemented locally. Backend README specifies exact request authorization, response/actions, versioned email normalization, private settings and bounded provider reads. Verification saves a signed callback's minimal reference before provider lookup and uses the existing finalizer. Resume uses the same saved order, a shared90-second recovery lease and15-second cooldown; expired/unresolved work never authorizes a replacement order. Post-commit wake hooks now cover checkout and verified callbacks as well as webhooks. Bad optional Google configuration is isolated from valid payment recovery.

Migration021_checkout_resume_lease.sql was tested in a rollback transaction first, then applied only to development with ledger guard and migration lock; production remains019.174 synthetic Python tests, website-role development rollback assertions, receipt SQL fixture, frontend build and compile pass. No hosted/payment-provider/concurrent-session proof or frontend integration is claimed. P3's public abuse/load tests, complete operator finance experience and real merchant acceptance remain outstanding; P4–P7 and remaining P2 operations still apply. Public booking and sending remain closed. This dated checkpoint supersedes the historical baseline table's missing-route inventory below.

A visitor selects a consultation and a genuinely available time, provides name/email/mobile, reviews the final price and pays once. The server confirms only authentic eligible payment. A delayed meeting, email or spreadsheet must not lose the booking or misrepresent its payment. Staff can see and resolve exceptions without asking the visitor to pay again blindly.

Build the final implementation on the existing permanent Sarsa resources. Fault-injection tests exercise that implementation; they are not a mock product or a second hosted booking journey. No promise of zero bugs or exactly-once network delivery: completion requires the concrete evidence below, with residual risks explained and assigned to an operator.

- Booking has no site email OTP. Email and mobile remain mandatory at browser and server boundaries. Bank/payment-provider authentication is independent.
- Appointment booking is primary; enquiry is secondary with its own verification and durable submission. No automatic discount modal, fabricated discount, marketing consent, SMS/WhatsApp or reminder campaign.
- English first; preserve a future translation boundary for Hindi without building a second language now.
- Retain approved content, organic/tactile visual direction, Madhuri Gupta's approved portrait and section-specific choreography. Do not reproduce the legacy UI or substitute another woman's portrait.
- Only004 edits.003 is a read-only behavioural reference; no shared credentials, runtime imports, records or client workbooks. Shared agency owner/login does not mean shared client data.
- Do not restructure imported projects, clean WSL/history, stop outreach processes, switch Codex accounts, or touch other Vercel projects as part of this work.
- Privacy/terms production pages remain the final content task as requested, before public opening. Their deferral does not excuse indefinite missing content or a claim of Google verification.
- Work continuously on independent authorised implementation. Ask the owner only for account-only actions, missing business decisions, paid changes, specific real transactions or unresolved cutover authority. Planning approval is not evidence that a live connection works.

## 2. Verified source baseline and evidence levels

| Area | Current local evidence | Remaining work / truth boundary |
| --- | --- | --- |
| Capacity, catalogue, anonymous admission | `policy.py`, `models.py`, `storage.py`, migrations001–014; interval claims, context pointer, durable admission and payment evidence | Real simultaneous-connection tests, final checkout HTTP integration and production capability proof |
| Payment | `razorpay.py`, `order_creation.py`, `payment_evidence.py`, `recovery.py`, `webhook.py`, `payment_policy.py` | Dedicated merchant absent per latest owner report; checkout/resume/verify routes not registered; hosted composition does not yet configure payment account |
| Hosting | `api/index.py`, `hosting.py`, `application.py`, `vercel.json` already define API-before-SPA and native Python entry | Not deployed. Canonical production host is pinned; preview URLs must fail closed instead of accessing production data |
| Google | `studio.py`, `google_oauth.py`, `google_access.py`, `google_workspace.py`, `google_records.py`, `google_delivery.py`, migrations015–019 | Owner sign-in/grants, correct-owner workbook creation, Meet behaviour and live delivery not yet verified |
| Email | `resend_email.py` bounded send transport; `email_events.py` signed minimized inbox; HTTP receiver mounted locally | No durable mail dispatcher, budget ledger, event projector or hosted callback acceptance |
| Background work | Payment recovery functions and one-job `/api/internal/google/run` | No permanent scheduler, complete wake-up routes, watchdog, operational deployment or worker-key handoff |
| Receipt | `queries/receipt_snapshot.sql`, `receipt_view.py` explicit allowlisted output | Email statuses currently job execution states; partial refunds currently collapse to `refunded`; correct both before public integration |
| Actual website | `frontend/src/App.jsx` HashRouter; `pages/Booking.jsx` OTP and legacy `/api/book-appointment`; `ContactPage.jsx` old transport; Render warm-up remains | Replace production callers together; reviewed HTML16 is not the live React booking implementation |
| Tests | Existing125 Python checks passed in preceding turn; recorded development rollback fixtures and frontend build | These are not concurrency, real provider, hosted runtime, restoration or inbox-delivery proof |
| Database | Manifest records001–019 applied/checksummed on both branches and closed intake at last verification | Recheck actual ledger/settings before next migration; this plan does not make a fresh live-state claim |

Reconfirm Git root/branch/diff before implementation or publication. Existing broad dirty work includes user/prior work and line-ending changes. Never stage all blindly or normalize unrelated files. Scope every commit to reviewed files and inspect repository workflows before any push. No automatic release-gate workflow is introduced; local correctness checks remain necessary. Any future publication must respect the user's no-GitHub-Actions preference and verify workflow trigger behaviour rather than assume a commit marker suppresses every event.

## 3. Settled configuration and remaining decisions

### 3.1 Settled owner decisions — do not ask again

| Item | Value |
| --- | --- |
| Public origin | `https://www.sarsajyotishsansthan.com` |
| Git / hosting | `NeuraFlowUser1/Astrologer_Madhuri_Gupta`; Vercel `neura-flow1/astrologer-madhuri-gupta`; owner performs dashboard actions under `neuraflowuser1@gmail.com` |
| Database | Neon `cold-art-76378232`, `neondb`, Singapore; exact branch/host/role IDs in manifest; website role `sarsa_booking_web` |
| Google Cloud | `sarsa-jyotish-sansthan-510008`; publishing status In production is owner-reported, not verification approval |
| Practice Calendar, client-owned workbook, reply address | `sarsajyotish@gmail.com` |
| Agency-owned separate004 workbook | `neuraflowindia@gmail.com`, no underscore |
| Email account | Existing Resend login `neuraflowuser1@gmail.com`, owner confirms Free |
| Email sender | `Sarsa Jyotish Sansthan <bookings@mail.sarsajyotishsansthan.com>`; verified sending subdomain per screenshot; receiving disabled; Gmail reply-to |
| Email secrets | Owner reports `SARSA_RESEND_API_KEY` and `SARSA_RESEND_WEBHOOK_SECRET` saved as sensitive Production-only Vercel settings; never request values in chat |
| Webhook | Owner successfully added Sarsa `/api/webhooks/resend` alongside003 despite published Free limit; preserve both; actual live callback not proven |
| Services | Kundli Matching ₹2,100; Kundli Prediction ₹2,500; Vastu Consultation ₹4,500; Numerology ₹2,100; INR; all30minutes |
| Hours | Monday–Saturday10:00–12:00 and15:00–18:00 Asia/Kolkata; capacity one; Google Meet for all online appointments |

Policy code currently uses30-minute notice,10-day advance horizon,10-minute hold and appointment-end+24h receipt access. Preserve these implemented reference defaults during development; record explicit launch confirmation if not already supported by an owner decision. Never silently broaden approval of days/hours into approval of cancellation/refund rules or unknown birth requirements.

### 3.2 Inputs collected just before the dependent work

| Dependency | Recommended route | Who / when |
| --- | --- | --- |
| Razorpay | Dedicated client merchant under owner's partner arrangement; verify activated account, merchant identity, live/test separation and supported reconciliation capabilities | Owner creates/activates; ask when payment account setup begins, not repeatedly during email work |
| Permanent scheduler | Dedicated Sarsa Cloudflare Worker with scheduled bounded calls to existing Vercel backend; database remains durable work authority | Confirm owned Cloudflare account, current capacity/cost and access before external provisioning; no reuse of003 worker/keys |
| Operational owner | Name person monitoring failures and manual payment cases; agree coverage and escalation address/channel independent of Resend | Owner decision before live acceptance |
| Scheduling rule | Staff record closures/manual commitments in protected studio before promising times; Google Calendar is downstream | Confirm practice accepts rule before public opening; external Calendar busy-sync is additional explicitly scoped integration |
| Service preparation | Specify which consultation needs birth date/time/place, whose details matching requires, and unknown-time treatment | Owner before enforcing service-specific mandatory fields; current optional fields must not become invented requirements |
| Cancellation/refunds/rescheduling | Written cutoff, fee/refund treatment, no-show and support procedure | Owner before enabling staff policy actions and final terms; implement safe primitives without inventing commercial rules |
| Shared email capacity | Determine other-project usage and reserve a safe Sarsa allocation including enquiry OTP | Owner dashboard evidence if unavailable to tools; no claim Sarsa alone controls team allowance |
| Backups/retention | Confirm approved encrypted destination, access owner, retention, acceptable data-loss and recovery windows | Prepare concrete proposal; approve before storing extra personal-data copies or scheduling deletions |
| Controlled real test | Exact amount, payer, date/slot, recipients and refund handling | Obtain later; ₹1/₹10 are suggestions, not approved amounts or verified minimums |

Do not ask for these all at once. No owner action is required to begin the next local email implementation slice.

## 4. Non-negotiable correctness rules

1. Database owns capacity. Availability is advisory; hold transaction revalidates price/version, service, interval, hours and current eligibility.
2. Lock order remains context → schedule → booking/order for capacity/financial paths. Delivery paths lock booking before job; never acquire context/schedule later from a job lock. Global expiry never clears context pointers in its schedule-first loop. New functions document and test their order.
3. Slot expiry does not resolve money. Keep one unresolved checkout/context until proved safe or explicitly resolved by authorised staff; another tab cannot bypass this using a new request ID.
4. A browser callback, closed payment window, failed individual payment attempt, empty local table or empty remote payment list cannot prove terminal unpaid status.
5. One finalizer validates merchant/mode/order/amount/currency and capture evidence, then saves financial observation, capacity decision and follow-up work atomically. Late/extra money gets a separate case; never steal another slot.
6. Provider calls happen outside database transactions. Lease tokens fence database completions; they cannot revoke already-issued network requests.
7. Distinguish confirmation, payment/refund facts, meeting state, email acceptance and recipient-server delivery. No email/read guarantee.
8. Unknown database commit/provider result remains uncertain and discoverable. Retry uses original immutable identity; no fallback creates a second payment, meeting, spreadsheet or email.
9. Public intake may close while status access, signed events, recovery and owed communications continue. Missing one optional integration must not unnecessarily disable unrelated financial recovery.
10. Customer-facing copy gives one sensible next action; never exposes internal errors or asks the visitor to diagnose the system.

## 5. Implementation packages and dependency order

Complete a package's code, migrations, adverse-case tests and documentation together. Apply additive migrations only after development evidence; never edit001–019. New migration numbers begin after the verified current ledger, provisionally020+, assigned at implementation time. All paths below are004-relative; new filenames are proposals, not claims they exist.

### P1 — Durable email delivery and receipt truth (local implementation complete; hosted proof pending)

**Purpose:** confirmations survive interruptions without duplicate sends, and the visitor sees truthful delivery status.

Existing seams: `resend_email.py`, `email_events.py`, `storage.py`, `application.py`, `hosting.py`, `queries/receipt_snapshot.sql`. Add focused `email_delivery.py`, `email_messages.py`, `email_reconciliation.py` and transactional functions; reuse `delivery_jobs`/`provider_inbox` rather than create a second queue system.

**Data contract and transaction design**

- Existing job identity `(kind, booking_id, recipient_role, booking_revision, event_key)` remains unique. Financial exceptions require their own stable event_key. Do not backfill or re-send old jobs from guesses.
- Add template_version, payload_hash, send_deadline_at, destination_revision, accepted_at and classified last_error where needed. Payload includes exact recipient, sender, reply-to, subject, text, escaped HTML and project/job tags. Freeze payload/destination atomically before first external attempt. No later template edit changes retry bytes.
- Keep execution state separate from delivery observations. Add append-only minimized email observations with provider/account/event uniqueness and job/provider association; add projected sent/delivered/bounced/complained/failed/suppressed timestamps or explicit equivalent columns. Do not overload Google `done` or generic mail `failed` to mean a customer bounced.
- Add a per-job budget reservation ledger, unique on job and allowance period. Count an ambiguous attempt conservatively once, not again for every retry. Preserve uncertainty across period changes; do not refund allowance based merely on a lost response. Provider quota responses still override any local estimate.
- `claim_email_delivery` selects only explicit email kind/role pairs, using booking-before-job locking, due time and expiring180-second lease. Suppress obsolete unsent jobs; quarantine invalid kind/payload rather than let them enter Calendar cancellation logic. Use bounded scans/SKIP LOCKED and indexes, with starvation tests. Send admission locks booking then job then budget-period row; never acquire booking/job under a shared budget lock. Event completion must not acquire booking after locking a job/inbox row. Review every new path against existing payment/Google lock order.
- Claim can freeze content before dispatch, but `first_attempt_at` is set only in a separate committed begin-send operation after eligibility, suppression and budget checks. A crash after this commit but before HTTP is conservatively ambiguous. Never reset this timestamp to extend retries.
- Recheck revision, cancellation and send deadline immediately before external send. If begin-send commit is unknown, do not send on that invocation. Later recovery reads persisted state. No database lock across HTTP.
- `finish_email_delivery` requires matching unexpired lease and frozen hash. Known success records provider UUID once; unique provider/account mapping prevents one message being assigned to two jobs. Stale completions do not overwrite newer state; preserve authenticated provider observations for later reconciliation.

**Messages and deadlines**

| Kind / role | Trigger and content | Deadline / exception behaviour |
| --- | --- | --- |
| booking_ack/customer | Confirmed eligible capture; consultation, time/timezone, amount and reference; no birth data/notes | Send while current confirmed appointment is in future; if too late, retain attention and support rather than send a misleading future appointment message |
| booking_ack/client | Same transaction; minimal reference/time and private studio instruction | Time-sensitive; late jobs become operator attention, not silently discarded |
| booking_details/customer | Current revision's verified ready Meet URL; self-contained details | Must precede appointment start; never send stale meeting link or block behind acknowledgement delivery |
| booking_cancelled/customer,client | Authorised cancellation revision; explicit refund status separate | Proposed24h relevance deadline; longer outage becomes staff review; business wording awaits policy |
| payment_review/client | One independent financial case/event | Never drop unresolved case because mail expires; message attempt budget/window may close while case remains visible to operator |

These are implementation defaults for review, not an advertised response-time promise. No customer reminders until timing/channel/quiet-hours and late-booking behaviour are agreed. Normal booking means three emails before enquiries/cancellations/exceptions; Google invitations must not silently add extra customer messages.

**Retry rules**

- One network attempt per leased invocation; timeout10s; fixed provider host; original `sarsa004/<jobUUID>` key and identical payload.
- Transport stops at23h from first attempt, conservatively within provider24h window. At/after cutoff, no automatic POST even with same key. Keep unknown outcome as attention; operator may reconcile using provider evidence, never click an unqualified retry button.
- Retry transient/uncertain work with bounded exponential backoff and jitter, capped15min and earlier than send_deadline/23h cutoff. Honour Retry-After where safely parsed; no immediate busy retry. Configuration/authentication/payload failures need correction, not repeated rapid sends.
- A later definite rejection does not erase an earlier uncertain acceptance. Accumulate evidence across attempts. Never switch to Gmail/SMTP or generate a new job ID to escape uncertainty.
- Shared team quota: Sarsa's ledger can control Sarsa consumption only. No guarantee about003 usage. Honour provider429, preserve due jobs, display operator warning, and cap/close new intake when critical delivery readiness cannot be sustained. Already-paid work stays recoverable. Do not purchase capacity silently.

**Delivery event reconciliation**

- Verify signature/raw body, deduplicate and commit minimized inbox before2xx as already implemented. Keep explicit sender/project filters and reject mismatched identity. Do not retain003 personal data from shared-team events.
- Claim Resend inbox rows independently from Razorpay with leases and bounded retries. Match signed project/job tag, frozen Sarsa sender/account and saved provider ID. Unknown/mismatched IDs remain quarantined or retryable, not auto-attached by email address.
- Event may precede HTTP success or a timed-out send. If saved provider ID is absent, only bind a signed provider ID to an existing begun attempt with matching immutable job tags; require uniqueness and no conflicting candidate. Preserve conflicts for review. Confirm actual provider event tags/shape in hosted test before enabling projection.
- Retain both event time and receipt time. A delayed `sent` must not erase `delivered`; a complaint/bounce must remain visible even if delivery happened earlier. A single numeric status ranking cannot represent these facts. Project each customer-facing field from observations and explicit failure precedence.
- Hard bounce/complaint creates scoped suppression for that recipient, with privacy-safe address key and audited release/correction policy. Do not futilely send details after a hard bounce. Signature delivery is not authority to mutate booking/contact facts.
- Missing callbacks leave accepted/unverified delivery, not fabricated delivered. Sending-only key may not permit message-status reads; do not broaden it silently. Provider dashboard/manual reconciliation is acceptable for exceptional unknowns; automated retrieval requires explicit supported permission design.

**Receipt correction:** current SQL treats any refunded_paise>0 as `refunded`. Add distinct captured/refunded amounts and partial/full refund projection without rewriting financial history. Preserve unresolved extra-payment cases separately from the accepted booking payment. Update Python enums, receipt projection, frontend contract fixtures, staff display and tests in the same slice; no unsupported new enum sent to an old frontend.

**Proof:** two workers one job; crashes before/after begin-send/HTTP/save; identical retry payload;23h boundary; early/duplicate/reordered/conflicting events; lease expiry and cancellation race; quota rollover/429/shared-usage uncertainty; bounce suppression; HTML/header injection; provider ID conflict; partial/full refund; unchanged booking confirmation when email fails. Run real development transactions rolled back plus concurrent-connection tests where required.

### P2 — Permanent scheduling, recovery and monitoring

**Purpose:** work continues after a visitor closes the page or a webhook is lost.

Selected architecture: database outbox/inbox remains authoritative. Dedicated Sarsa queue wake-ups trigger immediate bounded Vercel consumers; a15-minute scheduled Worker rescues missed publication or delivery. Queue messages are wake-up hints, not the only record of work. This replaces the earlier minute-polling/no-queue proposal for idle compute efficiency.

- Verify owned Cloudflare account before provisioning. Suggested client-local `workers/booking-recovery/` contains one explicit scheduled handler with fixed Sarsa URL allowlist, no arbitrary forwarding endpoint and no customer data in requests/logs.
- Use a15-minute rescue tick (`*/15 * * * *`), with immediate event-triggered processing between ticks; verify plan/cost and measured runtime. Each lane gets a bounded invocation: payment inbox/reconciliation, Google delivery, email sending/events, cleanup/heartbeat. Bound total tick concurrency to avoid exhausting database connections. Give time-critical meetings/email and financial cases priority with age-based fairness for Sheets.
- Each HTTP invocation processes a bounded count/time budget, stops below Vercel120s, and selects jobs server-side; caller cannot provide recipient/booking/amount. Initial per-lane single-job delivery and bounded payment batch reused from existing code; increase only with evidence. Worst-case backlog drain and near-appointment deadlines need explicit peak-load measurements, not a theoretical job count claim.
- Separate lane secrets; existing `SARSA_GOOGLE_WORKER_KEY` remains Google-only. Add email/recovery secrets through protected owner handoff after exact config exists. No reuse of receipt, studio, Google encryption or Resend keys. Constant-time exact bearer checks; bounded empty JSON request; no browser-cookie authority.
- Database leases absorb repeated/overlapping scheduler invocations. A transport retry is a new wake-up, never a new job. Expired processing jobs are eligible for recovery; counters and claims are not erased.
- Heartbeat records started/completed tick, lane outcome, backlog age, next due count, unresolved money age and provider errors without personal payloads. A separate watchdog must detect stopped scheduler; its own heartbeat is not proof of liveness.
- Initial operational targets: missed successful sweep>20min; paid meeting/details waiting>5min; any imminent appointment without meeting within60min; expired unknown email retry window; owner connection revoked; backup older than agreed interval. Measure latency and tune with actual coverage; no false2min promise with a slower schedule.
- Independent monitoring must not call a Neon-backed readiness/heartbeat route on its own schedule. The recovery invocation verifies backend identity and committed completion, then publishes a minimal non-personal completion signal to an independently observed destination outside Neon. Only verified completion refreshes success; attempts, partial failure and missing lanes remain distinguishable. The observer must detect missing signals even if the scheduler is completely stopped. A monitor implemented only inside that same scheduled handler is insufficient. Choose and verify the destination, external observer and alert channel before launch; no personal payloads, paid service or real alert message without applicable authorisation. This still detects database failure because the recovery cannot report verified success when its database work fails. The observer can run eight minutes after a sweep without querying Neon. Detailed database diagnostics occur on an actual incident or during the next recovery sweep, not as perpetual second polling.
- Enquiry OTP must have an appropriately fast dedicated delivery wake-up and short deadline; minute polling alone may be unacceptable UX. Keep durable OTP intent and measured sending latency, with scheduled rescue. Never claim a sent code before provider acceptance.
- Cleanup in bounded indexed batches: expire only unreferenced contexts and elapsed pseudonymous counters after retry horizons; retain unresolved financial/booking/job references. Retention periods require approved policy. No cascade deletion of live obligations.
- Verify Vercel plan suitability for this commercial client and costs; no automatic paid upgrade. Vercel Hobby daily cron is not suitable for minute-level recovery; do not add unsupported cron configuration.

**Proof:** missed/doubled tick, overlapping consumers, scheduler-only outage, lane starvation, provider timeout, revoked key, fake caller, database unavailable and restoration after downtime; measured no-traffic and peak resource usage; independent failure alert reaching approved operator. Keep all real sends disabled until authorised verification.

### P3 — Complete payment HTTP flow and operator-safe finance

**Purpose:** one coherent checkout, truthful recovery and no lost money.

- Add `/api/checkout`, `/api/checkout/resume`, `/api/checkout/verify-payment` to `application.py` using existing admission/order/evidence functions; do not create another finalizer. Compose a merchant/version-bound provider in `hosting.py` only from Sarsa settings.
- Validate context, Origin, receipt, request fingerprint and quota before mutable work. Same authorised request/body returns original outcome; changed body conflicts. Review current whole-email lowercasing before public use, preserve entered address for customer review, and version any normalisation change so existing request fingerprints remain valid. No silent spelling correction or claim of mailbox ownership. Persist admission before hold transaction; rate limits survive rejected holds.
- Receipt status/resume authenticates independently of a still-live context cookie. A context cannot disclose earlier booking identity to someone who lost receipt material. Server next_actions alone controls new-time/resume buttons.
- Server-owned quote binds existing policy version/service/time/amount/duration. No public amount, mode, recipient, merchant or test-discount override. Recheck database policy version and atomically pin order intent before HTTP.
- Resume existing order only after bounded/coalesced current evidence check; no provider fetch on every browser poll. Creation_unknown remains recoverable; receipt/order search must use documented provider pagination and identity, never assume order creation idempotency.
- Verify callback signature where supported, then fetch authoritative payment/order and pass canonical finalizer. Signed webhook is persisted first; incomplete/unknown outcome is recoverable. Browser success never confirms.
- After hold expiry, captured payment creates attention unless valid claim remains under explicit rules; do not backdate or take another person's slot. Additional captured payment has its own case. Preserve partial refunds, full refunds and disputes as separate financial facts.
- Pin original merchant/mode/credential version; rotation must retain supported lookup access. Missing old credentials leaves attention; no cross-client fallback. Compose optional integrations independently so bad mail settings cannot unnecessarily disable valid payment webhook recovery.
- Dedicated merchant setup: owner creates/activates; confirm identity/currency and exact key names from code, save secrets privately; register only implemented signed payment events after hosted route acceptance. Test/live data isolation is enforced inside all lookups/finalizers.

Rate-limit baseline from migration011: context20/hour, availability60/minute, receipt30/minute, checkout30/hour per scoped pseudonymous key; admission adds6 distinct attempts/context/hour. These replace older proposed5/10min figures as source facts, not validated launch limits. Verify exact key scope and shared-network behaviour, bound global capacity abuse, and do not silently add ownership challenges.

**Proof:** every C03/C04/C08 and R4 race, same-context new request after expiry, two contexts same slot, changed body/receipt, lost order response, delayed capture/refund, incomplete pagination, duplicate payment, key rotation, closed intake with owed recovery, and incompatible service quote. Use independent DB connections to demonstrate overlap exclusion and bounded deadlock retry, not just sequential rollback fixtures.

### P4 — Google completion and correct-owner records

**Purpose:** one correct meeting and separately owned client/agency records.

- Reuse current Studio OAuth and role-bound encrypted grants. No Google consent through Codex's account as a substitute. After hosting works, user signs in as each intended owner separately and grants only that role's scopes.
- Verify refresh/reconnect revision fence, revoked access, wrong account, state replay and expired session. Encryption-key rotation retains decryptability for existing connections; backups alone cannot decrypt without separately recoverable keys.
- Provision workbook only through that owner's consent and intended Drive identity. Verify actual owner, distinct workbook IDs and004 label, not visibility in another Drive account. Keep003 workbooks untouched.
- Current fixed `Booking history` layout/RAW row writes must detect modified header/tab/occupied row and ownership changes. At9999 booking rows, surface capacity before exhaustion and add an explicit rollover migration/owner mapping if needed; no silent overwrite or unbounded resizing. Separate human reporting views from machine-maintained rows.
- Ambiguous workbook creation searches original intent; never issue another blind create. Quarantine ambiguous matches and guide owner selection using supported app access; do not guess file identity.
- Calendar deterministic event ID, immutable private properties, times and current revision checked on every reconciliation. Pending Meet is distinct from ready. Cancel uses stored event identity/revision and conditional update semantics; no mass search/delete.
- Define record completeness: bookings, subsequent status changes, payment/refund references and project identity mirrored through versioned snapshots/events. Current booking-only rows are not a complete cancellation/refund history. Add new job identities/row assignments for changes without mutating already-frozen historical rows. Full authoritative state remains Neon.
- No birth details or private notes in email or external meeting description unless explicitly necessary/approved; inspect exact existing payload before live test. Enquiry mirror contract belongs to P5. Workbooks are secondary business records, not transactional backups.

**Proof:** two owners, wrong owner, lost create response, repeated job, row conflict, deleted/revoked workbook, retry after reconnect, pending/invalid Meet, duplicate event409, past appointment, cancellation during create and stale worker cleanup. Real account/workbook/meeting tests only after exact owner/action agreement.

### P5 — Customer pages and durable Contact integration

**Purpose:** preserve the accepted design while keeping booking simple and eliminating legacy bypasses.

- Preserve existing HashRouter entry links `/#/booking?service=...` and `/#/contact`; service IDs allowlisted. Map accepted HTML16 to actual React route with one reducer/state owner, same-origin API adapter, schema fixtures and receipt helper. Never ship its sample adapter, simulated payment/receipt, reset switches or auto-tour.
- Four visitor steps: consultation → date/time → your details → review/pay. Six visual compositions retain their distinct purpose. Only factual server confirmation triggers receipt celebration.
- Approved numeric baseline from HTML16: forest#26483d, paper#fffdf8, plaster#f7f5ef, essential muted text#50624d; content max1220px; gutters40/20px; hero56/38px; section40/32px; body17/16px; help14px; inputs16–17px; buttons52px; panels24px. Use the approved Georgia/system-sans preview baseline for booking rather than silently imposing legacy Cinzel/Outfit; record any cross-site typography harmonisation separately before implementation.
- Hero starts after page readiness, no scroll prerequisite; other assemblies start once on viewport entry, not scroll progress. Initial unformed CSS precedes paint without permanently hiding content on script failure. Use accepted per-section timings3800/2300/2600/2100/2200/1800ms as reference, not a blanket animation on every form field. Focus/input interaction settles animation immediately; reduced motion immediate; errors and payment facts never delayed by animation. Auto-scroll is review-only and stops on user input.
- Mobile recap precedes form; stationary interactive targets; visible keyboard focus; screen-reader error associations/live status without countdown chatter. Check1440×1000,390×844,360×800,320px width and short landscape, zoom200%, reduced motion and slow network. Visual screenshots are required at implementation, not claimed in this planning pass.
- Required mobile uses existing server phonenumbers normalisation; frontend shares valid/invalid cases and country selection without pretending ownership verified. Keep drafts in memory; browser receipt storage holds opaque ID/secret only. Storage failure has an explicit recovery warning before payment; no analytics/URLs/logs with receipt or personal data.
- Abort and generation/request guards for date/service/quote changes. Preserve contact fields on availability failure. Server clock with monotonic elapsed countdown; visibility return reconciles. Expiry triggers status check, not reset. Bounded2→5→10s polling respects Retry-After; after60s stable checking/help, not failure.
- Unknown API schema/version/status shows recoverable error, never guessed confirmation. Loading, empty date, unavailable service and failed request are separate states. No default slots, zero fee, noon birth time or invented success.

**Contact is a real work package, not an incidental route move:**

- Port `/api/contact` and purpose-bound verification into separate modules and durable database records. Do not import the legacy monolith, SQLite fallback, generic OTP bypass or daemon-thread sending into the new app.
- Keep enquiry OTP until separately changed by owner. Store purpose/email-bound secret-keyed token digests, expiry, attempt/send counters and atomic consumption. Six-digit codes need a separate protected digest key, short TTL and bounded attempts rather than a plain fast hash. Encrypt frozen OTP message content at rest and erase recoverable codes after the short sending/verification window; retain non-secret delivery evidence under the approved retention policy. Validate the exact submitted token; existence of cached email is not sufficient. Duplicate submit replays only its own committed enquiry outcome.
- Save enquiry and delivery intents before acknowledging receipt. Form says enquiry received, not appointment booked. Optional phone remains optional here; booking email+mobile remain mandatory.
- Contact OTP uses short-lived protected content, rate limits, resend semantics and no plaintext code logging. Budget it within shared Resend allowance. Keep verification notices separate from booking-job FK constraints: add enquiry-owned records/jobs or explicitly typed purpose-specific tables, not fake booking rows.
- Define client/agency enquiry copies with separate owner mappings and004 labels; minimize message content, restrict access and include in retention plan. Email failure does not erase enquiry.
- Move Booking, Contact, EmailOtpModal and App warm-up together to explicit same-origin transport. Remove Render fallback only after callers migrated; retire both legacy booking creation aliases with410. Audit all CTA routes and footer/nav links. Contact regression tests must cover token mismatch/reuse/expiry, quota/DB outage and no false booking success.
- Homepage/Kundli/About/contact storyboard guidance remains authoritative for later visual production integration; this booking package is not permission to claim all other pages already migrated. Track each remaining page's approved content/motion separately in its existing design documents. No whole-site reorganisation or invented new page designs.

### P6 — Protected staff operations and safe policy changes

**Purpose:** unavoidable exceptions have an actionable, audited resolution.

Extend existing `/studio` rather than create another admin app. Establish explicit role capabilities: client manages appointments/closures; agency manages technical connections/records; any agency booking/financial powers require explicit approved role mapping. Session authentication alone does not grant every operation.

- Inbox: unresolved payments, lost/expired receipt cases, pending meeting, bounced/uncertain mail, failed Sheets, revoked account and stale worker/backup. Paginate/index; limit personal data by purpose. No public lookup by email/mobile/reference.
- Mutations use Origin/CSRF protection, fresh authorised session, operation idempotency ID, expected revision, audit actor/time/reason and transaction locks. Money operations require independent provider evidence; reference/contact knowledge alone is not identity proof.
- Closures/manual appointments claim capacity through the same schedule transaction and cannot displace holds/confirmed bookings. Batch closures report conflicts explicitly.
- Rescheduling atomically validates and swaps capacity, increments revision, suppresses unsent obsolete jobs, enqueues old-event cleanup and new meeting/details, and mirrors change history. Old meeting identity must survive revision changes until cleanup verified. Failure to obtain new slot leaves original booking intact.
- Cancellation releases capacity under policy, saves revision and cancellation jobs, but never claims refund completed. First release may record provider-dashboard refund evidence rather than introduce unreviewed automatic refund initiation; confirm scope before money mutation feature.
- Contact correction requires verified support procedure and audited destination revision; never edit frozen attempted payload. Revoke/replace relevant access safely and issue current correction only under approved send rules. No unauthenticated self-service change from bearer status receipt.
- Stale in-flight send can still arrive after cancellation; keep factual current receipt and controlled correction. Studio cannot reset uncertainty or assign a new idempotency key merely to make a dashboard green.

**Proof:** wrong role/session, concurrent revisions, operation replay, reschedule capacity conflict, cancellation during provider I/O, partial refund, stale destination, old meeting cleanup, immutable audit and sensitive-data redaction.

### P7 — Security, operational acceptance and controlled cutover

**Purpose:** prove permanent wiring and preserve existing commitments before inviting real customers.

1. Freeze reviewed release artifact/file list. Verify dependencies/lockfiles, Python runtime packaging, excludes, ASGI route behaviour, status codes/content types, no-store and canonical host controls. Test missing config fails safely and an optional bad integration does not take down unrelated recovery. Review Vercel commercial plan/resource eligibility and secret availability without printing values.
2. Build and test final source locally. Audit output excludes design-review controls/media not needed at runtime and secrets. Review receipt/SDK CSP, escaped messages, strict origins, secure cookies, request sizes, trusted proxy header, rate-limit fail-closed behaviour for new intake and privacy-safe logs. No request-body/debug logging of personal data/codes.
3. Recheck schema ledger and grants. Apply additive compatible migrations, then consumers/API, then producers/frontend. Keep public intake closed. Never run destructive fixtures on production. Preview deployment cannot borrow production credentials; production-pinned host remains a deliberate boundary. Hosted verification may require controlled closed-intake production deployment of the reviewed release, not weakening host checks.
4. Record deployment commit/artifact and rollback route. User's Vercel access is manual; agent prepares exact instructions and verifies reachable responses. Do not ask owner to redeploy old main merely because a secret was saved. Do not push to an unrelated factory dev/prod branch as a substitute for this client's main.
5. Verify `/api/booking-policy` JSON, private `/studio`, signed webhook failure/success behaviour, persisted callbacks, protected workers and actual database role. HTML200 fallback is failure. Resend webhook registered early: inspect its status/failures and replay only appropriate retained Sarsa events after receiver verification; do not disable003's endpoint. Shared-team retries may already exist even before Sarsa sends.
6. Owner signs in separately for Google roles; create/verify intended workbooks and one approved test meeting. Test renewal and private receipt data without exposing account credentials. Complete provider configuration/readiness evidence, scheduler/watchdog and operations runbooks.
7. Inventory existing Sarsa commitments under scoped permission: legacy storage/calendar/active payments. Preserve uncertain evidence. Freeze legacy new intake during final reconciliation; import occupied intervals without inventing payment or sending historical confirmations. Resolve overlap cases before public availability.
8. Perform agreed small real payment through protected expiring test quote, same final checkout/finalizer/meeting/mail route. No public discount/query bypass. Record real fees/refunds and financial trail; release test capacity explicitly. One success is not concurrency/restore proof.
9. Complete genuine `/privacy` and `/terms` pages and homepage links as final content task. Actual direct URLs must serve correct content despite HashRouter. Explain actual Google/Neon/Resend/agency copies and approved retention, policies and support; obtain owner approval. Recheck Google branding/scope requirements rather than assume publishing status suffices.
10. Verify backups through isolated restore, keys/grants through least-privilege checks and callback/worker configuration after restore. Restored environments have outbound sends disabled; rehearse against simulated provider history before any live recovery. Restoring an old snapshot can replay accepted messages after provider's24h window, so all restored uncertain sends require reconciliation before reactivation. Avoid automatic financial rollback or blind old-job replay.
11. Review evidence gaps and get concrete public cutover decision. Public opening must require correct policy/merchant/Google/mail/worker health and operator readiness, not an environment flag alone. Keep explicit closure control and post-launch observation window. Rollback closes intake/serves honest unavailable UI while compatible financial recovery remains active; never revive unpaid legacy booking creation.

## 6. Acceptance matrix — required evidence, not slogans

| ID | Must demonstrate | Evidence / exit condition |
| --- | --- | --- |
| A01 | No double capacity; no context checkout bypass | Independent simultaneous DB connections; one valid claim, deterministic conflicts, no unresolved orphan pointers |
| A02 | Crash-safe admission/order/finalization | Fault at every commit/HTTP boundary; original order retained; financial case not erased |
| A03 | Accurate refunds and extra money | Partial/full/extra-payment fixtures preserve amounts and separate appointment outcome |
| A04 | Durable, bounded email | SQL+transport tests including23h cutoff, quota, changed payload, early callback, stale lease and bounce |
| A05 | Correct Google identities and recovery | Both workbook owners proved; deterministic meeting retry and revision cleanup; separate004 records |
| A06 | Background progress and independent outage detection | Duplicate/missed tick, backlog/fairness, scheduler death, revoked credentials; operator sees actionable alert |
| A07 | Customer clarity and accessibility | Desktop/mobile screenshot review, keyboard/reduced motion, real API contract, no booking OTP/demo controls |
| A08 | Contact remains protected and durable | Exact token validation/atomic consumption, retry-safe enquiry commit, no thread-only success or SQLite fallback |
| A09 | Least privilege and privacy | Wrong role/receipt/Origin/key rejected, minimised payload/logs, keys absent from bundle/source and preview |
| A10 | Hosted app is actual backend | Permanent origin returns intended JSON/status; cookies/callbacks/workers/DB verified, no SPA masquerade |
| A11 | Operational recovery | Scoped restore drill with sends off, schema/key availability, reconciliation before replay, documented owner action |
| A12 | Controlled payment and cutover | Authorised real trace and existing-commitment mapping; no invented fees/refund; public opening reviewed |

For each result record date, exact code/migration revision, environment/resource, what was actually tested, outcome, unresolved limits and next owner. Do not count a fixture as a real provider success or an email acceptance as receipt/read confirmation. Run tests appropriate to changes, then frontend build for code edits; additional repetitions require changed code or an unresolved concern, not a ceremonial three runs.

## 7. Review findings resolved in this plan

| Finding | Tightening / implementation consequence |
| --- | --- |
| Revision3 said no backend/API/database while001–019 and native routes now exist | Source baseline now distinguishes local implementation, recorded database evidence and missing hosted acceptance |
| Shared Resend account treated like exclusive allowance | Budget design explicitly bounded to Sarsa; shared quota evidence and429 handling; no guaranteed free capacity |
| Successful second webhook confused with published plan entitlement | Record observed acceptance; no upgrade inference; verify actual delivery and preserve003 |
| Job state mistaken for recipient outcome | Separate immutable observations and customer projections; early callback and reorder rules |
| Later rejected retry could erase earlier ambiguous send | Attempt evidence is cumulative;23h cutoff tied to first committed attempt and never reset |
| Budget/claim time could start retry clock before eligibility | Explicit separate committed begin-send step; no provider call on unknown commit |
| Partial refund currently shown as full refund | Cross-layer amount/status contract change and regressions required before public UI |
| Optional configuration could disable whole composed app | Review and isolate provider readiness so financial recovery survives unrelated mail failure |
| Contact left as vague follow-up | Dedicated durable enquiry/OTP migration with schema, quota, authority and caller-cutover proof |
| Sheets creation mistaken for complete record history or backup | Require versioned changes/capacity handling; independent backup/restore |
| Worker endpoint mistaken for scheduler | Dedicated permanent wake-up service, ownership prerequisite, measured cadence and independent watchdog |
| Proposed queue could add unnecessary paid infrastructure | DB outbox plus bounded scheduled wake-ups selected; external queue only if evidence requires it |
| Staff actions and refunds unspecified | Explicit role/revision/audit/capacity rules; policy input and money authority preserved |
| Restoring DB could replay old externally accepted work | Restore with sends off; reconcile provider effects before enabling consumers |
| Whole site described as done from HTML demos | Separate approved storyboard/design reference from actual production route integration |

Review passes completed for this document: source/configuration reconciliation; transaction/network/concurrency failure analysis; customer/Contact/design downstream analysis; scope/account/cost/release review; final cross-document/link consistency check. These are planning reviews, not implementation guarantees. Outstanding owner/provider decisions are named in3.2 and are not concealed by claims of airtightness.

## 8. Recommended next execution and update discipline

P1 local implementation and the P2 scheduler component are now recorded in the execution checkpoints above. Complete protected configuration, hosted/concurrency/monitoring acceptance and remaining P2 operational work; P3–P6 integrate the final customer and staff journey with permanent services. P7 proves and opens it only after concrete prerequisites are satisfied. Work on independent code when an account handoff is pending.

For each slice update manifest current summary, verification results and003 improvement register with files, tests and remaining hosted proof. Mark shared candidates separately from004-specific choices. Never apply004 no-OTP/business defaults to003 without a separate approved audit. Record discovered003 issues as source risks unless actually reproduced; ownership visibility alone is not proof of incorrect Drive ownership.

## 9. Provider facts checked for this revision

- [Resend idempotency](https://resend.com/docs/dashboard/emails/idempotency-keys): keys retained24hours; this implementation uses conservative23h retry cutoff. Do not claim indefinite duplicate prevention.
- [Vercel cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing): Hobby is daily with imprecise timing; unsuitable for proposed minute-level recovery. Actual Sarsa plan/cost still needs confirmation.
- [Cloudflare Worker limits](https://developers.cloudflare.com/workers/platform/limits/): Free limits include100,000 requests/day,10ms CPU,50 subrequests/request and5 cron triggers/account. Lightweight wake-ups are a candidate, not evidence of available capacity or ownership; benchmark and inspect account before deployment.

Other provider capabilities (merchant activation, permissions, minimum payment, Google ownership and live webhook payload) require their specific implementation-time verification. No unverified account-specific entitlement is assumed.
