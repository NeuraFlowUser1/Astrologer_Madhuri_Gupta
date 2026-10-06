# Historical handover commands

These commands belong to each contained package at `appointment-system/tools/handover.py`. They are offline owner operations, never web routes or application startup work. They do not send provider messages, create orders, enable booking or deploy anything. The installation must already have its checked canonical schema and immutable project settings. The existing system remains the source until the fenced conversion commits.

## Private inputs and reviewed selections

Supply the migration login through `BOOKING_MIGRATION_DATABASE_URL` in the private process environment. The normal connection checker verifies its host, database, login, transport protection and installation. Never put its value in arguments, source files, logs or this document.

The non-secret `--specification` file has exactly these fields:

| Field | Meaning |
| --- | --- |
| `version` | Integer `1`. |
| `installation_id`, `environment` | Exact values from this project's installed settings. |
| `source_layout` | Currently proved published layout: `legacy-003-16` or `legacy-004-31`. Later candidate layouts remain refused. |
| `writer_roles` | Exact old runtime login names to fence, one to twelve distinct names. Ownership, inherited privilege and schema-change permission are independently inspected; a supplied name does not make a privileged login safe. |
| `receipt_formats` | Published 003/16 requires exactly `receipt-003` and `enquiry-003`; it never issued owned checkout-context credentials. Published 004/31 requires `receipt-004`, `context-004` and `enquiry-004`. Values select existing named readers from the normal protected settings. Never invent a missing old key or infer readers from token length. |
| `recovery_reader` | Existing named assisted-recovery reader, or `null` when no such source records need translation. |
| `enquiry_code_formats` | `null`, or for a Sarsa source `["<existing code cipher reader>", "<existing code digest reader>"]`. An unfinished, unexpired code requires these readers. Conversion checks the original encrypted code and digest, protects the same code with the new keys, and preserves its expiry, attempts, generation, receipt and input. It never marks an unfinished enquiry verified or extends a code's lifetime. |
| `mail` | `null`, or `{ "credential_version": "<existing version>", "contact_message_formats": null }`. For retained encrypted enquiry messages, the latter is `["<cipher reader>", "<digest reader>"]`. These are names, not keys. |
| `google` | `null`, or `{ "calendar_client": "<existing client ID>", "resource_formats": {"<historical purpose>": "<registered reader>"}, "full_grant_reader": null }`. A retained Sarsa full-grant reader selects its exact entry in `BOOKING_LEGACY_GOOGLE_GRANTS`; its existing key bytes are reused privately. |

`preview`, `diff`, `prepare` and `convert` load and validate the same protected payment, booking, contact, mail and Google configurations as the application. They reject missing selected readers before writing. A `null` adapter does not discard its records: translation refuses a nonempty source needing that adapter.

The published AstroAdvice verification rows do not contain the context and recoverable code payload needed to reconstruct a common challenge safely. `preview` and final `convert` refuse with `legacy_verification_continuation_required` while any old customer challenge or unused grant remains unexpired. They do not shorten its expiry, delete it or silently turn it into history. A refused conversion rolls back its writer fence and target writes. Recheck after the existing system has completed the work or its original lifetime has elapsed; never edit customer deadlines to pass this check. If an active challenge must cross the changeover, its supported continuation remains required before release. Login sessions are different: they are intentionally retired and require fresh sign-in.

`checkpoint`, `complete` and `abort` need the migration connection and reviewed selection identity, but do not need payment keys, sending keys or old decryption keys. `journal-only` additionally uses the separately declared journal login and `BOOKING_JOURNAL_KEYS`. It proves the real journal's installation, environment, database, login and release before advancing.

## An unreadable historical calendar permission

The explicitly approved reauthorization route uses the existing company resource
consent flow. Select `google.calendar_reauthorization: true` only for
`legacy-003-16`; `resource_formats` must be empty and `full_grant_reader` must be
`null`. `calendar_client` must be the same registered active calendar client.
Omitting the option preserves the normal requirement for the exact old reader.
Missing keys never automatically select this route.

The converter retains the exact owner, Google subject, client and scopes. It seals
the old opaque ciphertext as **unusable history** with a separate protected
purpose and `reauthorization-required` format, and marks the connection
`google_reconnect_required`. This is not a decryptable legacy-token reader or a
successful connection. Calendar refresh refuses it without a provider request,
even if its error marker is cleared. Existing event IDs, meeting links and
bookings continue through their normal exact conversion. No new event, calendar,
workbook or notification is created by this disposition.

Keep the current application and permission unchanged during preparation. During
the agreed short changeover, after imported records are verified and the common
company page is serving on the official domain, use its Calendar connection
action to obtain fresh Google approval. Use the same account and registered web
client. The existing consent flow pins the retained subject, checks the owner,
client, scopes, browser state and current company session, then requires the
initiating company session to confirm the returned permission. A different
subject is rejected. A Google callback alone does not install the grant or turn
booking on. The existing calendar event mappings must be checked again before
activation; successful conversion alone does not satisfy this release gate.

If the owner cannot approve or the new permission fails verification, leave the
new installation OFF and report the connection as requiring attention. Do not
infer consent, erase the old encrypted record, generate a replacement calendar,
or resume legacy writes after conversion. Plan owner availability before starting
the maintenance boundary. No consent link can be used until this official-domain
callback is actually serving and its exact address is registered with Google.

## Sequence

Run from the project's own root using its installed Python environment. These examples contain no credentials. `<...>` denotes a value from inspected metadata or a saved command result, not a literal default.

1. `python appointment-system/tools/handover.py preview --specification <reviewed-selections.json>`
   - Uses one read-only, repeatable snapshot. It does not fence old writers, save target records or create a handover.
   - Reports source table counts and hashes, planned target counts, explicit source dispositions and release/installation/schema identity. It prints no customer rows, email addresses, protected tokens or message content.
   - Save the JSON output to a protected operating evidence location. Its hashes are evidence, not permission to skip the final read. New encryption can produce different target byte digests from unchanged source facts.
2. `python appointment-system/tools/handover.py diff --specification <reviewed-selections.json> --baseline <saved-preview.json>`
   - Repeats the read-only preview and compares the source counts and table-content hashes.
   - Rejects another installation, release or schema baseline. A same-count content change is still reported. No record body is printed.
3. `python appointment-system/tools/handover.py prepare --specification <reviewed-selections.json>`
   - Saves one prepared handover with declared payment/mail account identities, writer set, source layout and release digest. Retained payment credential versions for one merchant/mode share one account identity.
   - Record the returned handover `id`. Preparation does not pause or deploy the old website.
4. After the planned provider ingress handover is actually serving and old admission/worker pause is ready, run `python appointment-system/tools/handover.py journal-only --specification <reviewed-selections.json> --id <saved-id>`.
   - The command checks the database journal. It cannot by itself prove that the public webhook URL routes to it; the separate hosted ingress probe remains required.
5. `python appointment-system/tools/handover.py convert --specification <reviewed-selections.json> --id <saved-id>`
   - Takes the final locked source snapshot, fences old writers, translates and inserts records, and checks target readback in one transaction.
   - A failure rolls that transaction back. Never assume failure from a lost connection; use `checkpoint` below.
6. Inspect the saved `imported` checkpoint and conversion evidence. Then run `python appointment-system/tools/handover.py complete --specification <reviewed-selections.json> --id <saved-id> --expected-digest <reviewed-target-digest>`.
   - Rechecks the actual saved target, source and writer fence. Only then prepares the narrow retained-source privacy behavior and marks completion.
   - Booking stays OFF. Hosted release, provider/account checks, projection acknowledgement and protected activation are separate required steps.

## Interruption and rollback

After a lost command response, run `python appointment-system/tools/handover.py checkpoint --specification <reviewed-selections.json>`. With no `--id`, this returns the latest saved handover for this exact installation. With `--id`, it requires that exact record. It rejects a different release, source layout or writer set and prints only bounded metadata. A missing latest record returns `null`; a missing explicitly requested ID is an error.

Use the returned `phase` to decide which step remains. Do not issue another `prepare`, `convert`, payment, email or activation merely because the previous terminal stopped displaying output. Repeating completed transitions remains refused; inspection is separate from mutation.

`python appointment-system/tools/handover.py abort --specification <reviewed-selections.json> --id <saved-id>` only aborts before import and only when no unprocessed buffered notification needs resolution. It cannot reverse an imported/complete handover or turn an old writer back on. After canonical writes begin, recovery follows the checked forward-repair/restore procedure; never overwrite newer payment facts with an old snapshot.

The command emits stable failure codes without printing raw driver/provider exception text. An interrupt explicitly directs the operator to inspect the checkpoint. No status from this tool means that a Vercel deployment, Cloudflare route, Google approval or real provider delivery has been verified.
