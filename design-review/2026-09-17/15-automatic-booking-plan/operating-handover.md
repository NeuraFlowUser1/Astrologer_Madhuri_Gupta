# Sarsa operating handover

## Purpose and evidence

Keep the live service understandable for the practice and recoverable for support. These are operating instructions for the implemented system, not claims that every exceptional real-world case was tested. Production is Sarsa's existing Vercel project and dedicated Neon production branch. Separate client/agency Google grants and workbooks are retained. No Project003 resources or customers are used.

The owner-operated1 INR test passed payment capture, confirmation, Google Meet, both separately owned record-copy jobs, delivered booking emails, rescheduling, cancellation and a full provider refund. Normal prices are restored. Recorded evidence is in verification.md and qa/2026-09-30-hosted-wiring-evidence.json. Keep the labelled test history; deleting financial/audit records is not part of this work.

The October1 non-design reliability pass adds506 passing individual tests, actual concurrent/restore/Chrome database proof and independently measured≥90% line/branch coverage in six domains. Its [completion report](qa/2026-10-01-reliability-strengthening.md) defines scope and limits; [local instructions](../../../tools/verification/README.md) provide one explicit repeat command without a publication/CI gate. The cryptography50.0.2 security update preserves saved keys and older encrypted data; apply the reviewed website revision once through Sarsa's separate Vercel account before treating that dependency as live. Existing daily backup scheduling and account ownership are unchanged.

## Normal staff routine

1. Sign in to /studio with the practice account. Review appointments and the Practice Inbox. Current date-selection/dashboard ergonomics are recorded for redesign; do not mistake that deferred work for a different booking backend.
2. Open an appointment to move or cancel it. Read the saved outcome before repeating an action. If a reply is uncertain, use the same-request check offered by the interface. Do not create a second request to guess whether the first worked.
3. Cancellation frees the appointment but does not refund money. Make approved refunds through Sarsa's Razorpay merchant, then wait for the saved provider evidence. In the Practice Inbox section below the calendar controls (heading “Know what needs your attention”) → Needs attention, open its payment item, add a note and use “Close review after verified full refund”. A review note alone does not close the case. The closure button verifies the recorded full refund; it does not issue another refund.
4. For failed saved work, read the exact issue before choosing “Retry saved work” or “Check payment again”. A queued retry is not proof of delivery or financial settlement. Check the later outcome; escalate repeated or unexplained failures with the booking reference and safe error wording.

## Contact corrections and lost access

Find the booking using its complete reference. Staff must first call the original saved mobile and verify payment details with the customer. Never tick that declaration without the actual call. If the original number is inaccessible, keep the case for manual review; do not substitute a caller-supplied number as identity evidence.

“Restore lost booking access” issues a short-lived code to give during the verified call. The customer opens /booking-help and enters it. Do not send the code in a URL or ordinary email. Correcting email/mobile is a different action for a confirmed future appointment; it replaces old receipt access and queues updated provider records. A cancelled test cannot prove that active-appointment correction path. Preserve the booking's fee, time and payment unless an explicit corresponding staff action is intended.

## Background work and alerts

Cloudflare runs Sarsa recovery every15 minutes and also handles queued wakeups. Its public /health reports recent recovery health without touching Neon. The independent GitHub monitor reads that health address at minutes8,23,38,53; it does not query the database or deploy the website. Check failed runs and the staff Inbox instead of assuming silence means success. Provider messages may arrive after the booking itself confirms.

GitHub monitor/backup jobs use the existing public repository with an exact-name/public-visibility guard. If visibility changes, scheduled work is skipped until an authorised budget-compatible configuration is reviewed. No paid plan or extra included-minute allowance has been authorised. Keep the100 included-minute/month limit. Review workflow activity and recent successes monthly; schedules may be delayed and inactivity can disable them. Do not create artificial commits to mask that condition.

Resend is shared with Project003. Sarsa keeps20/day and600 over31 days; enquiries have their additional8/day and240 limits. The approved Project003 correction allocates80/day, verification60/day and2400 over at least31 days. Its release is tracked in AstroConnect PR22. These shares fit the provider limits; unrelated sends or inbound mail still consume the same account. Review actual shared usage before increasing allocations. Retry only through saved work; do not resend accepted messages manually to work around an unknown response.

## Backup and recovery

Daily encrypted backup runs at08:32 India time into Sarsa's own Drive. See tools/backup/README.md for accepted runs, owner/key custody, restore checks and safe failure handling. Retain the password-manager recovery key and existing protected application settings. An archive alone cannot replace application encryption keys or Google permissions.

The first archive/restore/readback passed with19 migrations. Production now has31 verified migrations. The current-release checkpoint passed production export, full31-migration isolated restore and authenticated Sarsa-owned Drive readback without overwriting that earlier daily copy. A new checkpoint must always pass full current-schema restore before acceptance. The approved rule keeps30 UTC dates and one newest verified archive for each of the latest12 calendar months, always preserving the current verified copy and at least two newest copies. Remove at most20 older verified app-owned archives per successful run, rechecking their exact identity first. Unknown or unverified copies and unrelated files remain untouched. Storage exhaustion still needs investigation; no paid upgrade or broad deletion is authorised.

For disaster recovery, restore and verify in isolation first, recreate restricted database access, recover the existing application keys and review pending payment/email/calendar work before restarting workers. Never replay external actions blindly: reconcile their saved provider identities and outcomes first. Never restore directly over the live database merely to test an archive.

## Acceptance, final publication and deferred work

- Completed: provider-verified full-refund review closed through one normal Studio action, with the provider evidence and staff note saved.
- Completed: owner reports PASS for the development-only two-connection contention check. A separate database read confirms its temporary synthetic rows were removed. The private password/output did not pass through Codex.
- Completed in the authorised isolated fixture: confirmed dummy appointments, staff sign-in state machine, receipt replacement/redemption, old-access rejection, contact correction and blocked-time reopening. Actual HTTP and PostgreSQL ran unchanged; Google identity and external responses were synthetic. The corrected meeting, old meeting deletion, both separately owned record copies and three email requests completed without duplicate requests. No real call, payment or customer notification was needed. Real staff identity verification remains required for actual customers.
- Completed: final policy wording published/deployed; official privacy asset and privacy/terms/booking-policy routes verified.
- Scheduled operation: retain dated checkpoint/restore evidence and monitor continued daily backups. A one-time passed check cannot promise indefinite unattended operation.
- UI/UX: separately redesign the account entry, compact calendar/dashboard, date/time pickers and horizontal controls per dashboard-redesign-requirements.md. No redesign is included in this functional-completion pass.

These limits do not switch off normal booking or enquiry intake. Permanent signature checks, account separation, double-booking protection, private access and retry rules remain active.

## Temporary-record maintenance

Migration031 is installed on the pinned development and production branches. The existing recovery worker accepts old seven-lane and new eight-lane plans; the final website deployment advertises maintenance only when due. One bounded pass removes at most500 Google attempts,500 expired staff sessions and500 request counters older than24 hours past expiry. Sessions with remaining Google attempts are preserved. Booking, payment, receipt recovery, connection and audit history is outside this function’s authority. Overlapping passes safely skip; failures remain visible and retry through the existing15-minute schedule.
