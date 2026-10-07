# Booking experience refinement

## Current boundary

This release implements the owner-approved booking-experience refinement in the neutral master and complete, independent project copies. The original imported client work is preserved. Source-bound qualification, visual results and per-installation publication/provider observations belong to the programme evidence under `001-implementation-evidence/2026-10-07-booking-experience`; earlier released-package proof does not qualify a different source digest. The owner authorized complete booking-only qualification, agent visual review and controlled publication without another design checkpoint. New live payments/emails still require specific authority.

## Ownership and receiving-site files

The contained package owns booking policy, draft lifetime, verification, intake, payment/receipt recovery, date/time behavior, receipt facts, PDF generation and requested email-copy logic. The receiving website owns its React instance, brand, layouts, colors, labels, host entry and dependency lock. A project does not import the factory or another project. Copy the entire verified package through `tools/install/package.py`; never copy just selected engine files.

`docs/examples/booking-ui-adapter.mjs` is the thin adapter reference. Install exact receiving-site peers `react-aria-components@1.21.1`, `@internationalized/date@3.12.4`, `pdf-lib@1.17.1` and `@pdf-lib/fontkit@1.1.1`. Adjust only contained paths, the local bookingBrowser import, brand and theme. The adapter supplies its own React and named accessible-control exports. PDF/font modules load only on an explicit document request. The contained Source Sans 3 font and its license must travel with the complete package and be classified as booking-exclusive assets.

## Draft lifetime and operation authority

The public service-state response remains exactly `enabled` and `activation_epoch`. Browser-only state distinguishes a verified result, a brief check, and an unavailable result. `displayAllowed` retains an exposed form during a check; `admissionAllowed` blocks new booking, payment, code and receipt actions until verified ON. `retainView` permits a previously mounted draft to remain hidden and inert after a failed check. Verified OFF clears retention and removes booking DOM. A newly visited route cannot use retention to mount an unverified form.

No names, contact fields, birth details or typed codes are saved in browser storage, URLs or analytics. Deliberate refresh starts a new draft. Existing protected committed receipt access and signed payment evidence keep their separate recovery behavior. A callback arriving during a display check is saved first and retried through the existing recovery listener when fresh ON arrives; no replacement payment is made. No additional recurring timer is introduced.

Five-second visible-page service checks remain bounded to two seconds and 1,024 response bytes. A coalesced foreground return rechecks policy and relevant slots without blanking the draft. Unchanged quote, verification binding and exact selected slot preserve review and proof; changed policy/slot invalidates only affected decisions. Ordinary checks do not close an open draft selector. Its controls use `viewAvailable`; provider and commit actions still use admission authority. Actual OFF or unavailable view dismisses controls.

## Optional email and birth preparation

Booking verification owns the email requirement: OTP ON means email required and verified; OTP OFF means email optional. Required-contact membership is canonicalized from that one switch. Invalid supplied email is always rejected. Contact enquiries retain their independent verification requirement.

New intake explicitly uses normalization version 3 and represents absence as NULL. Omitted or version 2 intake still requires email; version 1 retains its historic lowercase and fingerprint behavior. Existing committed retries are located before current business-policy rejection. The legacy conversion model remains distinct and mandatory. Bootstrap/setup preserves previously saved company decisions; it does not update live policy from an edited JSON file.

AstroAdvice makes birth date optional for all its current services. There is no new birth field for Sarsa. Private contact correction follows the appointment's frozen email rule, rather than today's OTP setting. NULL email produces no automatic customer email job or Calendar attendee, while payment, practice Calendar/Meet, staff notification and both spreadsheets remain required. Current and legacy spreadsheet adapters emit a blank email cell rather than JSON null or a fabricated address.

## Controls and site presentation

The accessible controls use the official React Aria primitives supplied by the receiving site. Clicking any date/time field opens its chooser. The calendar is anchored to the complete field. Each picker uses the library's supported portal-container option with a fixed viewport host, avoiding a receiving website's positioned-body offset while retaining official positioning, focus, Escape and outside-dismiss behavior. The empty host cannot intercept pointer input; only the library's actual overlay children can. Its host is removed on disposal. A viewport-width change dismisses the menu while retaining the saved field and date navigation; a subsequent field click opens it against the new layout. Height-only keyboard changes do not force dismissal. Native month/year/time selectors have explicit accessible names. Birth date supports a direct year/month jump with no invented age floor; time offers all 60 minutes and an explicit Apply/Clear/Cancel choice. Unavailable dates come from the practice's current schedule window, not client-side invented availability.

AstroAdvice keeps its existing layout and adds 16 pixels above the booking introduction. Sarsa replaces the large introduction with one clear title and four vertical steps. Deliberate service click, Enter or Space advances to date/time; arrow-key radio navigation does not scroll. URL initialization does not scroll. The step strip follows the measured header height; section navigation respects both heights, reduced motion and user interruption. The existing useful booking help and site links remain.

## Receipts and PDF

Both inline confirmation and standalone receipt use `receipt-fields.mjs`. They show authoritative service/time/zone/duration, agreed fee, captured/refunded amounts, reference and honest meeting/email states. Missing or unsafe Meet links never erase valid financial facts. A practice-arranged meeting is not presented as a missing Google link. Old additive projections are readable but cannot enable new actions without their revision/mode/copy contract.

PDF generation requires confirmed owned facts and verified ON before and after lazy module/font loading. Compare only printed facts; changing email delivery alone does not invalidate the document. An older concurrent observation cannot replace a newer known receipt. Changed facts discard the candidate and ask for another deliberate request. The A4 document contains no customer contact details, receipt secret, staff note or provider secret. It renders the rupee sign with a subset embedded font and includes only a validated Meet link annotation. This is appointment information, not a tax invoice or a claim of a tagged accessible PDF; the HTML facts remain accessible.

After the final authorized read, local Download/Open links last at most five seconds and recheck admission synchronously on click. OFF, unknown state, changed facts and disposal revoke the Blob URL. The PDF action has its own busy state and never makes a payment or sends email. The original receiving-site static and general-route assets remain outside this booking-only action.

## Requested email-copy contract

POST `/api/checkout/email-details` accepts exactly request_id, nonzero operation_id, strict positive expected_revision, and optional email. It requires current installation/ON, the owned receipt secret, exact browser origin and the existing checkout request limit. It does not require an expired checkout cookie.

For a booking with an email, use that saved address; a copy request cannot redirect it. For a no-email booking, require a valid address for each new deliberate request. It is copy-only data, not a contact correction. Normalize and freeze the body before submitting. Unknown commits retain the same operation and destination for explicit retry. Authenticate and check ON first, then replay an existing matching operation before checking current revision, resources, confirmation or quotas. A changed body under the same ID is a conflict. Accepted revision and current receipt revision are separate.

The existing delivery_jobs table gains only nullable `receipt_copy_request` metadata. It contains exactly version=1, operation_id, expected_revision, input_fingerprint and accepted_at. Event identity is receipt:<operation>. Identity, destination and deadline are immutable from insertion, including before the first send attempt. Use existing worker claims, mail account binding, provider idempotency, callbacks, suppressions and recovery. Never send directly from the HTTP route.

At most three accepted requests per booking per rolling day, with 60-second cooldown. Pending/unknown sends block another copy; uncertainty never expires into permission to duplicate a possibly sent message. A job waits at most 30 seconds per existing worker wake for its Google link without consuming a provider attempt. Its deadline is the earlier of receipt expiry and 23 hours after acceptance, checked before meeting wait or sending. A definitively expired unsent job needs attention and requires a new deliberate request. A revision/cancellation before first send supersedes it.

Public email_copy has exactly nine bounded fields: operation_id, booking_revision, state, has_booking_email, target_hint, next_request_at, remaining_requests, can_request and blocked_reason. Only a masked hint is public. States are not_requested, pending, processing, provider_accepted, delivered, superseded and needs_attention. Provider acceptance does not mean delivered. Invalid storage replies remain uncertain; successful commits remain saved if a wake fails.

## Privacy, access, backup and changeover

Copy-only destinations and frozen transport payloads are protected booking-delivery data under existing access and backup boundaries. This refinement adds no blanket erasure promise or retention policy. No new table, scheduler, knob, credential or Google approval address is introduced. Runtime roles cannot read/write tables directly; only the web capability may request a copy. Helpers are private, owner-controlled routines with fixed lookup paths. OFF denies the new endpoint, selectors, receipt pages, dedicated chunks and font without disturbing general enquiries or private company tools.

Migration 036 is append-only. The first 35 migration files must remain byte-identical. Backup's 95-table allowlist is unchanged by the added column/index/routines. Isolated encrypted backup and independent provider-disabled restore verify NULL contacts plus queued/settled immutable copy rows.

Future hosted sequence: preserve settings and backup; company OFF on both; run the protected schema installer separately; coordinate compatible API/workers/complete websites and release bindings; revision-check each existing saved policy into the canonical rule while OFF without changing prices or chosen verification controls; prove OFF, host assets, access and new-schema recovery; only then restore the intended ON state. Import/startup verifies the package and never migrates a database. Vercel accounts stay disconnected. The latest owner publication instruction authorizes this controlled changeover after qualification; it does not authorize extra customer emails/payments or connection of deliberately disconnected Vercel accounts.

Before nullable intake, old publication may be restored only if its contracts remain compatible. After NULL or copy rows exist, keep OFF and use the compatible repaired runtime or the agreed backup recovery route; do not run an obsolete worker/reader against new state, weaken constraints, fabricate emails or rewrite an applied migration checksum.
