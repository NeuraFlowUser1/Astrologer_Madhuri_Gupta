# Sarsa operating handover

## Purpose and evidence

Keep the live service understandable for the practice and recoverable for support. These are operating instructions for the implemented system, not claims that every exceptional real-world case was tested. Production is Sarsa's existing Vercel project and dedicated Neon production branch. Separate client/agency Google grants and workbooks are retained. No Project003 resources or customers are used.

The owner-operated1 INR test passed payment capture, confirmation, Google Meet, both separately owned record-copy jobs, delivered booking emails, rescheduling, cancellation and a full provider refund. Normal prices are restored. Recorded evidence is in verification.md and qa/2026-09-30-hosted-wiring-evidence.json. Keep the labelled test history; deleting financial/audit records is not part of this work.

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

Resend is shared with Project003. Sarsa's local limits are20/day and600 over31 days; enquiries have their additional8/day and240 limits. These do not reserve shared provider capacity against Project003 usage. Review actual shared usage before increasing allocations. Retry only through saved work; do not resend accepted messages manually to work around an unknown response.

## Backup and recovery

Daily encrypted backup runs at08:32 India time into Sarsa's own Drive. See tools/backup/README.md for accepted runs, owner/key custody, restore checks and safe failure handling. Retain the password-manager recovery key and existing protected application settings. An archive alone cannot replace application encryption keys or Google permissions.

The first archive/restore/readback passed with19 migrations. Production now has30; a future new daily archive has not yet supplied that newer-schema live proof. No automated archive deletion is authorised. Storage exhaustion must be investigated; do not buy capacity or delete copies automatically.

For disaster recovery, restore and verify in isolation first, recreate restricted database access, recover the existing application keys and review pending payment/email/calendar work before restarting workers. Never replay external actions blindly: reconcile their saved provider identities and outcomes first. Never restore directly over the live database merely to test an archive.

## Remaining acceptance and deferred work

- Completed: provider-verified full-refund review closed through one normal Studio action, with the provider evidence and staff note saved.
- Completed: owner reports PASS for the development-only two-connection contention check. A separate database read confirms its temporary synthetic rows were removed. The private password/output did not pass through Codex.
- Practice/customer: live assisted receipt recovery after genuine saved-number verification. Contact correction's real provider acceptance requires an eligible confirmed future booking; local database/browser checks already cover it. Do not create another paid appointment or fake a call solely to tick this item.
- Completed: final policy wording published/deployed; official privacy asset and privacy/terms/booking-policy routes verified.
- Scheduled operation: observe a future daily30-schema archive and retain first accepted19-schema evidence; monitor actual continued service rather than promising indefinite unattended operation.
- UI/UX: separately redesign the account entry, compact calendar/dashboard, date/time pickers and horizontal controls per dashboard-redesign-requirements.md. No redesign is included in this functional-completion pass.

These limits do not switch off normal booking or enquiry intake. Permanent signature checks, account separation, double-booking protection, private access and retry rules remain active.
