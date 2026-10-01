# Sarsa test and deployed-service audit — 1 October 2026

This is the earlier inspection snapshot. Its coverage and remaining-assurance findings are superseded by the later [completed reliability pass](2026-10-01-reliability-strengthening.md), which records the measured baseline, added tests, security update and final proof. The dated hosted/provider observations below remain historical evidence.

## Scope and conclusion

This is an inspection and rerun of the existing tests, plus read-only checks of the final deployed website, production database, background processing and backups. No application feature, production appointment, payment, provider permission or customer message was changed. Frontend redesign remains separate.

The current counts, individual database fixture names and hosted snapshots are also recorded in [the structured evidence](2026-10-01-test-coverage-evidence.json). Previous checkpoints are explicitly separated below.

The inspected release is `50f26fe004717ed100ec8244df6fd8cc864b2024`; its last application change is `e5928295054d0b8fe9084ac452fa36dd6dd793e4`. The owner reported the final Vercel deployment Ready. Current hosted behaviour independently confirms the new eight-lane recovery plan, configured services, normal prices, working public routes and protected staff/internal routes. The separate Vercel account is intentionally not connected to Codex; an exact Vercel deployment ID/source-hash response was not obtained through that account.

All existing checks rerun below passed. There is meaningful coverage of financial integrity, appointment conflicts, access restrictions, retries and recoverability. This does **not** establish complete bug coverage or a fully automated release gate. No coverage percentage is available, and passing mocked provider tests is not equivalent to real provider acceptance.

## Fresh automated results

| Suite | Current result | What it establishes |
|---|---:|---|
| `backend/booking_engine/tests/test_*.py` | 245 passed | Pure logic and HTTP/component tests: validation, receipts, payment evidence, sessions, staff permissions, enquiries and delivery/recovery decisions. Many replace the store or external transport. |
| Frontend booking/contact/protocol/route tests | 21 passed | Browser-storage and API-contract logic, identity/money checks, safe links, uncertain responses and preserved retry state. These are Node tests, not rendered-browser journeys. |
| `workers/booking-recovery/worker.test.mjs` | 26 passed | Scheduling, queue/retry bounds, independently progressing lanes, authentication, privacy, health monitoring and old/new-plan compatibility. |
| `tools/backup/test_*.py` | 34 passed | Encryption authentication, destination checks, transfer/retry handling, restore command safety and retention decisions. |
| `tools/worker-settings/test_*.py` | 6 passed | Strict private-setting handoff and scheduling-plan identity/shape checks. |
| **Total individual tests** | **332 passed** | Counts are not a measure of code coverage. No skipped/cancelled/todo Node cases; Python runs reported OK without skips. |
| Actual PostgreSQL integration/permission fixtures | 27 groups passed | Existing SQL assertions and generated production-query checks, run against all 31 source migrations in an owned network-isolated PostgreSQL 18 container. Each fixture was rolled back. |
| Production build | Passed | Vite built the app and generated public-route metadata/sitemap. |
| Existing frontend lint | No errors; 6 warnings | Two intentionally standalone browser-function snippets and four unused imports in the unrouted legacy Testimonials file. This is not a warning-free result. |

The historical September 30 total of 316 included 11 Project 003 quota tests. Today's 332 individual tests are Sarsa-only and include the frontend and handoff suites. SQL groups, browser visits and live checks are reported separately rather than added to that count.

### Actual database tests rerun

The 18 standalone fixtures were: calendar, contact intake, contact delivery, Google refresh, Google workbooks, independent payment handling, request limits, reservation, staff cancellation, staff receipt recovery, staff rescheduling, staff support, Studio calendar, Studio sessions, Studio inbox, temporary cleanup, core database constraints and website permissions.

The nine generated checks exercised the application's actual receipt query, payment recovery, Google delivery, workbook connection query, email-event replay, email dispatch, checkout-resume lease, recovery-plan query and shared booking/enquiry email allowance.

Examples of asserted failures include an overlapping booking or manual closure, cross-context checkout access, stale or wrong worker leases, unverified full refunds, agency/wrong-session staff actions, exhausted email allocations, duplicate events and overbroad database privileges. Cleanup checks cover bounded batches, referenced/live sessions, the grace period and repeated empty passes. The container had no network access and was removed with its volumes after exact ownership-label verification. Managed-Neon role names in the local permissions fixture are test-only NOLOGIN roles; live permissions were checked independently.

The independent-session Neon contention check remains **owner-reported passed**, with independently verified fixture cleanup. It was not rerun or directly observed by Codex in this audit. Single-connection SQL overlap assertions are additional evidence, not a replacement claim for that concurrent run.

## Fresh hosted and provider evidence

- Chromium opened all 13 distinct routes: home, about, services, four service pages, booking, contact, privacy, terms, booking-policy and Studio. Every route returned 200 and its expected heading. No browser page errors occurred. Studio's unauthenticated status request returned the expected 401.
- At 390 × 844, both remaining service pages, booking, contact and Studio loaded without horizontal overflow or page errors. This is mobile emulation, not physical-device or Safari/Firefox acceptance.
- Public booking-policy returned 200 with `no-store`; prices were the normal ₹2,100 / ₹2,500 / ₹4,500 / ₹2,100, each for 30 minutes using Google Meet. The temporary ₹1 test price is absent.
- Unauthenticated staff status and internal planning requests returned 401 with `no-store`.
- The authenticated, read-only configuration report marked all 11 integration groups configured and all five Google/staff format/separation checks true. Its explicit `provider_acceptance: not_checked` is preserved: this endpoint proves setup checks, not successful calls to every provider.
- The authenticated recovery snapshot exposed eight recognised lanes, no immediate pending work and `attention: false`. This is a point-in-time backlog report, not a promise about future deliveries.
- Production contains all 31 migration versions with hashes exactly matching the inspected source.
- Cloudflare's independent health endpoint returned 200/healthy. The three latest observed GitHub monitoring runs succeeded, including [run 36818139286](https://github.com/NeuraFlowUser1/Astrologer_Madhuri_Gupta/actions/runs/36818139286). These checks read the Cloudflare health signal, not customer data or Neon.
- Today's first scheduled daily backup, [run 36809105655](https://github.com/NeuraFlowUser1/Astrologer_Madhuri_Gupta/actions/runs/36809105655), succeeded from this source revision. Its log reports 34 backup tests, encrypted upload/readback, and successful isolated restore. Retention removed zero eligible old files; this is not evidence of a live old-archive deletion. Earlier current-schema checkpoint and idempotent-rerun evidence remain in the September 30 report.

## Database security and RLS

Production has 35 application tables, **zero tables with RLS enabled and zero RLS policies**. Therefore there are no RLS-policy tests to claim. This application routes customers through the server; it does not expose a customer database connection or rely on per-customer database roles.

Access is enforced through authenticated HTTP sessions/receipt capabilities, record-bound server/database functions and the restricted application login. The existing tests exercise these boundaries. Fresh live role inspection confirms that `sarsa_booking_web` has no superuser, create-database, create-role, replication or bypass-RLS capability; it cannot create application-schema objects or delete/truncate bookings. The separate backup role can read bookings and cannot insert, update or delete them. The local website-permission fixture also attempts and rejects protected operations.

This is an access-control model with tests, not an RLS implementation. Adding RLS would require a deliberate identity/context design and independent tests; turning it on indiscriminately is not a substitute for the existing access controls. Direct customer database access must not be introduced without reviewing that model.

## End-to-end evidence and its limits

Existing September 30 evidence records a real paid booking, Meet setup, separate client/agency spreadsheet copies, delivered signed email events, a staff reschedule, cancellation, full ₹1 refund and staff refund-review closure. Those provider/customer actions were not repeated in this read-only audit.

The approved synthetic support journeys used the actual browser, HTTP application and restricted PostgreSQL role. They proved receipt replacement, contact correction, redemption, rejection of old access and closing/reopening unavailable time. External Google identity and Google/Resend responses were substituted/captured. They therefore prove application-to-database integration and downstream consumer behaviour, **not** a fully automated real-provider E2E suite or real inbox delivery. See the dated [functional completion evidence](2026-09-30-functional-completion-evidence.json) and [fixture instructions](../../../../tools/booking-checks/README.md).

## Remaining assurance gaps

1. There is no single checked-in release command that provisions the isolated database, runs every SQL and rendered-browser fixture, executes the individual suites and fails if any expected suite is missing. Several browser checks are standalone functions with a fixed local port or fixture injection, not discoverable test-runner cases. Legacy hash routes still have a tested migration path; their existence is not itself evidence of a broken page.
2. GitHub currently automates monitoring and encrypted backup checks only. Application regressions are not automatically tested or enforced before deployment. No new build/release workflow was added; the existing user restrictions and usage budget remain unchanged.
3. No measured line/branch coverage, coverage threshold or maintained feature-to-failure-case matrix was found. Test count cannot substantiate a claim to cover most possible bugs.
4. There is no repeatable Firefox/Safari/physical-phone test matrix or formal automated accessibility audit. Current hosted checks used Chromium at desktop and emulated mobile widths.
5. No representative load/soak test, broad automated security scan or independent penetration-test evidence was found. Existing negative/retry/concurrency tests cover important cases, but not production-scale contention or every combined outage/recovery sequence.

Recommended next work: first consolidate the existing checks into a repeatable, explicitly complete **local** release verification command and a risk-based coverage matrix. Then extend the missing outage, concurrency, browser and security cases according to that matrix. Use isolated synthetic data; keep live payments, identity approvals and customer sends separate. Provider diagnostics must distinguish configured, accepted and actually delivered states. This improves repeatability without adding an unapproved GitHub release pipeline or changing the website's design.

## Repeating the current individual suites

From the application root, with the project's declared Python requirements and Node/npm dependencies installed:

```sh
python -m unittest discover -s backend/booking_engine/tests -p 'test_*.py' -q
python -m unittest discover -s tools/backup -p 'test_*.py' -q
python -m unittest discover -s tools/worker-settings -p 'test_*.py' -q
env -u NODE_TEST_CONTEXT node --test frontend/tests/booking/state.test.mjs frontend/tests/booking/protocol.test.mjs frontend/tests/contact/protocol.test.mjs frontend/tests/routes.test.mjs workers/booking-recovery/worker.test.mjs
npm run build
npm run lint --prefix frontend
```

Verify the individual Node test count rather than accepting five file-level results as 47 executed cases. These commands do **not** automatically execute the SQL or rendered-browser fixtures. They require the separate controlled fixture setup described above. Do not point destructive or synthetic database fixtures at production.
