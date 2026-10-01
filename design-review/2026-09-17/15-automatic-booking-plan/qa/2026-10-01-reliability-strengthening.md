# Sarsa reliability strengthening — 1 October 2026

## Result and release boundary

The approved non-design pass is complete locally. **506 individual tests passed**, plus real PostgreSQL contention/permission/recovery checks, encrypted restoration and Chrome-to-API-to-database journeys. Each measured domain independently meets **90% executable-line and decision-branch coverage**. The production build passed. No UI redesign, production identity/payment bypass, application publication gate or GitHub build/release workflow was introduced.

The runtime change is a defensive encryption-library upgrade from cryptography **48.0.1 to 50.0.2** in backend and backup requirements. Existing operational keys/accounts stay unchanged. Deploy this reviewed main revision in Sarsa's separate Vercel account to activate the backend dependency update. Local proof does not establish that Vercel already installed it. The existing daily backup reads the updated GitHub requirement on its next run.

Baseline source: `50f26fe004717ed100ec8244df6fd8cc864b2024`. Exact counts, source hashes and separate proof records are in [the structured evidence](2026-10-01-reliability-strengthening-evidence.json). This supersedes the coverage/repeatability gaps in [the earlier inspection audit](2026-10-01-test-coverage-audit.md); dated real-payment/provider evidence remains historical.

## Coverage and test counts

| Independent domain | Baseline lines | Final lines | Baseline branches | Final branches |
|---|---:|---:|---:|---:|
| Booking backend | 88.81% | **95.51%** | 76.83% | **90.52%** |
| Backup helpers | 57.25% | **95.31%** | 50.50% | **91.09%** |
| Protected worker-setting helpers | 67.26% | **99.11%** | 47.37% | **94.74%** |
| Customer booking/enquiry logic | 35.98% | **99.47%** | 30.71% | **92.44%** |
| Staff logic | 0% | **99.67%** | 0% | **92.91%** |
| Recovery worker and observer | 95.65% | **98.55%** | 88.51% | **97.97%** |

The Python baseline uses original individual suites. The JavaScript baseline runs the original 47 native Node cases with the same final Istanbul collector and denominator. Zero staff baseline means those cases did not execute staff scripts; earlier standalone browser acceptance is not erased. DOM counters are merged across contexts. Unvisited files stay at zero; test code and libraries never count as application execution. The complete functional Booking page is included, so its inline form/receipt decisions are measured.

Coverage excludes other marketing-page composition, CSS, decorative motion, static artwork/copy, design-review prototypes and the retired unrouted legacy backend. SQL/PLpgSQL and PowerShell have direct assertions/handoff evidence, **not** a fabricated percentage. The server-only database has no RLS policies; restricted-login and record-access tests are its relevant permission proof. This is not 90% coverage of every visual website file or possible bug.

| Suite | Passed |
|---|---:|
| Backend Python | 284 |
| Backup Python | 60 |
| Protected worker-setting Python | 11 |
| Customer/staff/worker JavaScript, including original 47 once | 151 |
| **Total** | **506** |

This adds 174 cases to the 332-case baseline. Direct SQL groups, browser journeys and hosted reads are reported separately.

## Feature-to-failure proof

| Risk or feature | Fresh proof |
|---|---|
| Competing appointment requests | Independent PostgreSQL connections genuinely overlap. One reservation wins; an adjacent time remains available. A separate 40-request burst through eight workers produces exactly one winner for the chosen slot. |
| Lost replies, repeated clicks and refresh | Actual booking/enquiry hooks and staff scripts preserve the original operation/body after uncertainty; explicit rejection releases only that operation. Polls/cooldowns are bounded. |
| Incorrect/delayed payments | Evidence/checkout tests reject wrong merchant, order, amount, signature and conflicting events; resumed checkout retains ownership/receipt. No actual charge is made. |
| Abandoned background work | Parallel consumers receive distinct live leases. After expiry a replacement worker can claim the work, while the abandoned worker cannot finish it. Pending work remains visible after restoring the database. |
| Meeting, mail and record copies | Synthetic provider-boundary tests cover temporary failure, partial durable work, retry-window exhaustion, owner/layout mismatch and saved revisions. Lanes progress independently. Earlier actual Meet/Sheets/mail acceptance is separately dated. |
| Enquiries | Actual hooks/forms check input, uncertain reconciliation, verification/resend limits, bounded polling and safe writes. Booking keeps mandatory email/mobile with no email OTP. Shared booking/enquiry allowances are tested in SQL. |
| Staff support and appointments | Actual scripts reject malformed/oversized responses/unsafe links, render private values as text, retain uncertain changes and ignore late replies after sign-out. Chrome plus real restricted SQL proves correction, receipt redemption, rejection of old access, rescheduling, cancellation and reopening. |
| Restoring encrypted data | All 31 migrations are dumped, encrypted, authenticated and restored offline. A separate fresh TLS database reconstructs checked permissions. The actual application accepts the correct receipt, rejects the wrong one, preserves one captured payment/occupied slot and discovers recovery work. |
| Invalid backups and retention | Oversized/truncated/wrong-project archives, export/restore failures, ambiguous destinations and ownership/space failures are rejected. Invalid/unverified copies cannot release retention. Cleanup targets exact owned resources only. |
| Operator warnings | An actual failed scheduled monitor email was found in the intended NeuraFlow inbox and matched to its GitHub run. Subsequent scheduled checks succeeded. No production failure was manufactured. |

The current runner executes all 26 direct SQL/query groups against all 31 actual migrations in a new labelled local database; protected direct table/function attempts are included. It accepts no caller's database URL. In Chrome, only Google's identity response is synthetic: the actual bound callback, secure cookie, session and role checks still execute. External traffic is intercepted. No fixture route or bypass is present in the deployed application.

## Security, compatibility and actual warning receipt

The Python audit initially reported six advisory aliases representing three unique upstream cryptography issues. The affected certificate/PKCS7 routines are not Sarsa's exposed Fernet/AES-GCM path; the update removes an outdated dependency defensively. The final full production Python resolution has zero known advisories, and the production npm audit has zero. These are dated advisory checks, not independent penetration testing or protection against unknown vulnerabilities.

A public labelled synthetic vector generated with 48.0.1 proves 50.0.2 reads the older encrypted archive and Google-grant formats. It contains an invented fixed key/text, never a client key or record. All backend/backup tests and actual local restores passed with the replacement. A separate clean environment with only the backup's two declared dependencies also passed all 60 backup tests, checking its effect on the existing daily job.

The rebuilt public output was scanned across 26 text/bundle files for private keys, database passwords, payment/API keys and private-setting patterns; none matched. No operational value, raw mailbox content or private resolution/advisory report was added to Git. Production frontend dependencies are unchanged; new dependencies are test/development-only. Two existing development transitive packages received compatible lockfile updates.

Lint has zero errors and six unchanged legacy warnings: two standalone browser-function snippets and four unused imports in the unrouted Testimonials file. New test warnings were removed. The current FastAPI/Starlette test adapter emits an upstream future HTTP-client deprecation warning; tested behaviours pass. That adapter migration is later maintenance, not a current production failure.

The scheduled [monitor failure run 36754123687](https://github.com/NeuraFlowUser1/Astrologer_Madhuri_Gupta/actions/runs/36754123687) finished on September 30 at 17:49:26 UTC. Its matching GitHub notification arrived in `neuraflowindia@gmail.com` at 17:49:47 UTC. Account, repository/workflow/run and receipt timestamp were verified without changing labels or exporting the message body. Recent scheduled runs 36827403655, 36825154433 and 36822789076 succeeded. GitHub scheduling/mail remain external services with possible delay; this proves a real receipt, not every future alert. Existing schedules, public-repository guards, Neon wake frequency and the owner's included-minute budget are unchanged.

## Repeat and proceed

[The checked-in runner/instructions](../../../../tools/verification/README.md) provide one explicit local command for all suites, direct SQL, both thresholds, production build and Chrome/committed-SQL proof. This is intentionally not a mandatory publication or CI gate. Generated reports/fixture handoffs are ignored; safe dated evidence is checked in here.

The final full runner passed. The final portable Chrome runner was separately rechecked after refinement. Staff and receipt pages had no horizontal overflow at 390 × 844 and no Chrome page errors. The temporary fixture's PostgreSQL timestamp needed explicit conversion to India time; that test-only conversion was corrected and rechecked. Production time handling was unchanged. No actual customer send, identity grant or charge occurred.

No new agreed functional omission was found in this pass. Deploy the reviewed dependency update, then perform read-only hosted checks and return to the approved UI/UX overhaul. Do not claim a new paid real-provider E2E, unlimited capacity/long-duration soak, independent penetration test, physical-phone acceptance or zero-bug outcome. Earlier real ₹1 booking/refund acceptance is historical evidence, not repeated here.
