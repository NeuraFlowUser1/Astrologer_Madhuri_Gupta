# Sarsa recovery and independent monitoring

**30 September2026 live checkpoint:** dedicated Worker `83b28f4b-c203-477b-992c-14037e33424a` is deployed with the agreed15-minute rescue, existing queue/KV and all four original protected settings. Actual12:00 scheduled heartbeat is healthy, and an authenticated empty-system queue pass completed without retry/failure codes (CPU3ms/wall629ms); public health returns200/healthy. Fixed the native edge runtime’s rejection of redirect:error by using redirect:manual and rejecting all non200 responses, preserving credential non-forwarding. Twenty-five Worker tests, native synthetic200/302 cases and the required frontend build pass. Unknown/private errors are replaced by fixed codes. Worker fix and independent monitor are published as `c529cfc`; first monitoring job passed. Google owners and separate workbooks are accepted; real sends/Meet/payments remain separate checks. Older checkpoints below are historical.


## Purpose and current state

Earlier30 September2026 recovery check, superseded by the live checkpoint above: this Worker was still an unpublished component. All four owner-selected existing Vercel keys have been privately captured, checked for distinctness, encrypted for the Windows user and readback-verified. No live value was regenerated or provider setting changed. The Sarsa Vercel account remains intentionally disconnected. Configure the existing dedicated Cloudflare resources through private process input after the canonical backend is served, then prove authenticated matching; local capture alone is not live acceptance. Daily encrypted backups are live and tested, separately from this Worker and its still-unpublished monitor. See the canonical verification record for current release evidence.

Immediate queue hints wake the permanent website's saved work. A15-minute scheduled sweep rescues lost hints and expired queue retries. Saved database jobs and provider observations remain authoritative. No customer records, job IDs, provider payloads or credentials enter queue messages or heartbeat storage.

29 September2026: implementation and local verification complete for this scheduler component, not full P2 operational acceptance. Dedicated resources exist; Worker is **not deployed**, keys are **not configured**, GitHub workflow is **not published**, and real alerts/messages/payments have not been exercised. Website checkout/contact integration, payment account composition, retention cleanup, staff operations, hosted/concurrent/load tests and cutover remain in the canonical completion plan. This is the permanent implementation, not a second demo booking path.

## Owned resources

| Resource | Identity |
| --- | --- |
| Cloudflare owner | neuraflowindia@gmail.com |
| Account | 162c1ab1ba0619c1c78d9495f3260f18 |
| Worker name | sarsa-booking-recovery (deployed30 September; version above) |
| Queue | sarsa-booking-recovery, ID8d602c4b56f44eca8ae5bcfa6cde1fab |
| Heartbeat KV namespace | sarsa-booking-recovery-heartbeats, ID927be5fbe5c54002ae03e55c48a0a2e5 |
| Deployed worker origin | https://sarsa-booking-recovery.neuraflowindia.workers.dev |
| Website origin | https://www.sarsajyotishsansthan.com |

Wrangler account identity and account workers.dev subdomain were read live. Queue and namespace creation were acknowledged by Cloudflare. Existing003 script/queue unchanged. Billing subscriptions API returned403; Workers standard endpoint returned standard=true, which is not sufficient evidence of Free/Paid subscription or remaining shared allowances. No plan change, deployed worker, queue message or KV record was created during provisioning. Never recreate a resource blindly after an uncertain response; list exact names first.

## Exact behaviour

- Cloudflare cron: `*/15 * * * *` UTC, at00/15/30/45 each hour. One private `/api/internal/recovery/plan` request reads a minimal scheduling snapshot. If no near-term work exists, no queue message or delivery call occurs.
- Authenticated `/wake` accepts only an empty JSON object and publishes `{version:1,remaining:8}`. Fixed website/account destinations; no arbitrary URL, booking or recipient input. Invalid public requests do not touch Neon.
- Queue consumer: one message/batch, one consumer, seven one-job lanes at most per invocation, sequential provider calls. Contact email runs first, followed by payment events, payment recovery, Google, email events, booking email and Contact Google. Each pass has a90-second total deadline; each call uses only the remaining budget (and at most100seconds), no redirects,8KB response limit and exact004 identity checks. Email events may process one booking plus one enquiry observation. Errors do not stop other lanes while time remains; a long request can postpone remaining lanes. Seven calls plus two plan reads remain bounded; hosted timing/fairness/Free CPU proof remains outstanding.
- A lane call is only a wake-up: SQL claim/lease, provider duplicate-prevention identity and committed completion retain authority. Lease loss returns retry, not invented progress. A valid processed count is not proof of successful external delivery.
- Post-pass plan chooses a bounded delayed successor for unfinished work due within15minutes. A chain has at most eight successors; future retry timing comes from SQL, bounded to15minutes. Zero-progress due work waits60seconds to avoid a tight loop. Queue-level retries are three at60seconds. Exhaustion/expiry cannot remove the SQL obligation; cron rescues it later. Duplicate wake-ups are safe but still consume provider allowances; actual throughput and quota headroom require measurement.
- Existing signed Resend and Razorpay receiver hooks publish only after a matching saved event has committed. Ignored other-project Resend events do not publish. Failed/ambiguous wake publication logs a fixed safe code and preserves the successful event acknowledgement; independent rescue finds the row. No detached in-process task is relied upon. Checkout/callback and Contact start/resend/verify now attach the same committed wake hook.
- Payment lanes require explicit Accounts composition; hosted Razorpay credentials/merchant wiring are still absent and correctly return503. Scheduler planning can report empty payment lanes without making payment-provider calls. Health is not a public-booking-readiness check.
- Plan reports pending delays and one attention flag only. It honours live leases and creating-order grace. Attention covers recorded delivery attention, old failed/uncertain attempts, mail-budget blocks, unresolved payment cases, overdue work, errored old inbox events and imminent appointments missing a ready meeting or accepted meeting-details email. It does not claim delivered/read email. Staff acknowledgement/escalation workflows and full provider-specific diagnostics remain P6.

## Monitoring and costs

Only the scheduled sweep writes a heartbeat. Cloudflare KV key `sweep:<15-minute slot>` stores scheduled/completed timestamps and a healthy boolean, with24-hour expiry. Separate keys prevent an older sweep overwriting a newer slot. Publication failure or database error cannot record healthy success. Success means scan plus necessary wake publication completed; individual task success is independently checked through the attention projection. A delayed consumer can therefore take until a subsequent sweep to be reflected in this signal.

`GET /health` reads up to three KV keys and makes **no Vercel/Neon/provider request**. Missing/future/old/failed signals return503. A successful scheduled timestamp older than20minutes is unhealthy. KV eventual consistency may cause conservative temporary alarms; it must not be represented as immediate strongly consistent telemetry. Idle expectation:96 KV writes/day, up to288 reads/day for96 external checks, well below published individual Free KV allowances before shared-account usage; retries/manual checks add usage.

The independent GitHub workflow checks at08/23/38/53 each hour, eight minutes after rescue, using only `monitor.mjs`. Standard ubuntu-24.04 runner, one job, two-minute timeout, read-only repository access, no secrets, package installation, build, artifact, deployment, push or PR trigger. Checkout action is pinned to verified official v6 commitd23441a48e516b6c34aea4fa41551a30e30af803. Repository visibility was verified public via GitHub API. Public standard jobs use zero private-plan included minutes. Job-level exact repository and visibility=='public' conditions skip runner allocation for private/missing/fork metadata. Never change repository visibility just to obtain free minutes; if made private, monitoring stops and needs a replacement within the owner's100-minute/month cap. No billed fallback is configured.

GitHub schedules can be delayed/dropped and public schedules can be disabled after60days without repository activity. This is not a guaranteed alert SLA. No artificial keep-alive commits. The responsible operator must verify monitoring remains enabled and receives failure notifications; long-term unattended coverage beyond these limitations requires a separately approved independent service. GitHub failure notification destination/subscription and a controlled failed-signal alert still need live acceptance. The monitor is independent of Cloudflare/Resend but is not self-proving when GitHub itself stops running.

Neon estimate: one brief0.25CU wake every15minutes plus5-minute idle tail is approximately60CU-hours/30days. This is not measured use or a fixed quota guarantee; query duration, traffic, retries, higher compute size and development branches add usage. The observer adds no scheduled database wake-up.

## Protected configuration and deployment order

Four independent32-byte base64url settings belong in both the Sarsa Worker and Sarsa Vercel Production protected settings:

| Setting | Scope |
| --- | --- |
| SARSA_GOOGLE_WORKER_KEY | Google consumer only |
| SARSA_EMAIL_WORKER_KEY | Email sending/event consumers only |
| SARSA_RECOVERY_WORKER_KEY | Minimal scheduling snapshot and payment recovery lanes |
| SARSA_WAKE_KEY | Website-to-Cloudflare queue publication only |

Existing `tools/copy-google-protection-key.ps1` now accepts all four names. Generate each value once, save a protected password-manager copy and paste the same value into its two matching destinations. Do not rerun to obtain the second copy: that creates a different key. No value in source, chat, command arguments, logs or files. Existing receipt/Google/studio/Resend secrets cannot be reused. Malformed optional recovery/wake settings leave those components unavailable without disabling receipt/studio access. Wake URL is fixed to the verified dedicated account subdomain; no owner-supplied forwarding setting.

1. Production001–030 is applied/checksum-verified. The canonical backend, queue and protected key handoff are now connected. Complete the remaining hosted provider acceptance; emergency intake and delivery correctness controls retain their final operational role. Do not create new schema work solely for this handoff.
2. Prepare backend deployment and protected-key handoff together. Vercel owner neuraflowuser1@gmail.com performs its dashboard steps; do not switch Codex's Vercel account.
3. Put the reviewed Worker configuration and keys into the owned Cloudflare account and deploy only when the website private endpoints are ready. Wrangler config points to the real existing queue/KV namespace. Local `deploy --dry-run` is packaging proof only; it does not configure secrets or deploy.
4. Verify public `/health` never wakes Neon, private routes reject wrong keys, and a controlled saved-work event is recovered. Test stopped cron, failed lane, missing/expired queue hint and overlapping invocations. Observe actual latency/CPU/quotas; no real sends/payment without the agreed concrete test.
5. Publish the monitoring workflow to the existing default branch only after worker readiness. Ensure the owner receives failed-workflow notifications and verify one controlled failure and recovery. Publishing this file enables future scheduled monitoring, not a push-triggered release gate. Check the public-only guard with actual workflow context.
6. Record hosted acceptance, responsible operator and residual limits in the canonical verification/resource manifest. Provisioning and tests alone do not open public booking.

Local checks: run `node worker.test.mjs` from this directory; Python `unittest discover -s backend/booking_engine/tests` from client root; the development-only `recovery_plan_database_check` emits an actual-role rollback fixture. Never run that fixture against production. Required frontend compilation is `npm run build --prefix frontend`.

Sources reviewed29 September2026: [Queues retries/delays](https://developers.cloudflare.com/queues/configuration/batching-retries/), [KV limits](https://developers.cloudflare.com/kv/platform/limits/), [GitHub billing](https://docs.github.com/en/actions/how-tos/monitor-workflows/view-job-execution-time), [GitHub schedule limits](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule).


29 September Contact extension:21 worker tests pass; Contact mail uses SARSA_EMAIL_WORKER_KEY and Contact records SARSA_GOOGLE_WORKER_KEY. No new worker secret name or cron frequency. Backend migration024 is required by the expanded plan and consumers before deployment. Code expiry is due work in contact_email. Local packaging dry-run is separate from real deployment, queue draining and provider timing acceptance. No Worker or monitor was activated by this checkpoint.
