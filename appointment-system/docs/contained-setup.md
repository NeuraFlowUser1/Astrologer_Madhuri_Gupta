# Common contained setup

Run these commands with the project's Python environment from its project folder. Every command uses only that folder's complete `appointment-system` and `appointment-settings` copies. The factory is not imported. No provider connection or database change occurs merely by importing the website.

## Reviewed local procedure

1. Verify/install the complete release and prepare its project-owned host entry and worker configuration using `tools/install`. Preserve each project's declared identity and existing provider resources.
2. Provide `BOOKING_MIGRATION_DATABASE_URL` through the operator's protected environment. Its host, database, login and pooling choice must match this project's declared migration target. This credential does not belong in the normal website or worker environment.
3. Run `python appointment-system/tools/setup.py install-schema`. This verifies immutable migration checksums and installs missing schema changes transactionally. It does not initialize business settings, create company credentials, or activate booking.
4. Run `python appointment-system/tools/setup.py initialize`. The first invocation writes this installation's identity and initial business settings with booking OFF. Repeating it verifies identity and preserves the current business settings and mode. Updating the bootstrap JSON does not overwrite decisions already saved in the company controls.

5. After the declared dedicated database logins have been created in the correct project, run `python appointment-system/tools/setup.py register-logins`. The command registers only the purposes declared in this installation, including the journal when declared. All logins must exist first. Missing, mismatched or disabled registrations are refused atomically. Passwords are not displayed, generated or rotated by this step. Successful registration is not proof that runtime credentials have been connected; the separate runtime preflight still applies.
6. Run `python appointment-system/tools/setup.py enroll-company` in a private interactive terminal. Enter the company username and password when prompted. Password entry is hidden, and the password never becomes a command argument. This is first enrolment only; any existing company credential makes the command refuse, including after a response was lost. Normal password changes use the protected company controls.
7. Complete the protected settings/provider bindings, historical handover, inactive worker preparation and ON/OFF publication acceptance before the release action. The public switch is controlled through the password-backed company area. A setup rerun cannot re-enable a revoked caller, reset a working password or silently turn booking on/off.

## First display setting

Before using the booking switch, provision the worker's independent
`BOOKING_CONTROL_RECONCILE_KEY` in protected maintenance storage and the
installation's own worker. Never place this key in website settings, browser
code or monitoring jobs. With the saved setting OFF, run
`python appointment-system/tools/initialize_projection.py --operation <saved-operation-uuid>`
using `BOOKING_MAINTENANCE_DATABASE_URL` and the independent read, publish and
reconcile keys in the protected process environment. Retain the operation ID
and the maintenance key in the owner's encrypted recovery material.
The command reads the actual maintenance-authorized SQL snapshot, retains its
generation, revision and activation identity, initializes only an empty
worker object, and verifies both the signed acknowledgement and a fresh signed
read. It never writes SQL, issues a company command or enables booking.
Reusing the same operation after a lost reply is safe. A different operation
cannot overwrite an existing object. Pending ON intent, a later restore
generation, signature mismatch or concurrently changed SQL state stops setup
with an error. Ordinary company publication then owns subsequent switch changes.
The setup tool is owner-only local tooling. It does not create an extra web administration endpoint. It does not sign in to Google, send email, move money, publish, or infer provider accounts from another project. Errors expose a bounded reason code rather than SQL parameters, connection strings or password values.

First enrolment cannot reset an existing password. For verified recovery of a lost company password, use the separate [protected company recovery procedure](company-recovery.md). It checks the existing credential revision, preserves the operation identity on retry, revokes old sessions and records immutable evidence in the same transaction.

## Independent monitoring setup

With `appointment-system/engine` and `appointment-system` on the Python module path, run `python -m tools.install.monitor PROJECT_ROOT --expected-root PROJECT_ROOT --repository OWNER/REPOSITORY`. Both root arguments must identify the actual project Git root; the repository must be its explicitly reviewed GitHub identity. This local command creates `appointment-settings/monitor.json` and the identical contained `appointment-background-monitor.yml` workflow. It does not access an account, publish, execute a workflow or discover a key.

The result lists the later protected setup: repository variable `BOOKING_REPOSITORY` and secret `BOOKING_MONITOR_KEY` in the `appointment-monitor` environment. During the authorized hosted handover, use the same monitoring key as that project's worker, never a database, application, backup or other client's credential. Retire the reviewed old monitor workflow only after its replacement is prepared and checked; unrelated workflows are not removed by the tool.

The observer runs at minutes 08, 23, 38 and 53. Its scheduled job refuses a private repository, fork, wrong repository or non-main branch before allocating a runner, and rechecks eligibility before reading protected worker health. It checks website/process/display state without a database read. Conflicting owner files are preserved, generated files are written atomically, and an interrupted preparation can resume identical completed files. A changed profile or package prevents a success result. This is independent failure monitoring, not deployment or application testing on every publication.

## Verification

`tests/test_setup.py` checks actual PostgreSQL setup, identity rejection, transaction rollback, preserved dynamic settings, preserved revocation, first password enrolment and simultaneous enrolment. Six native methods passed on PostgreSQL 16 (`/tmp/abs-setup-final16.log`) and PostgreSQL 18 (part of `/tmp/abs-supplemental18.log`). `tests/test_setup_terminal.py` checks that missing hidden input, a mismatched password confirmation, cancellation and unexpected terminal errors cannot expose a password or connect to the database.

`tests/test_setup_contained.py` runs the shipped commands from a relocated copy after deleting its source master and blocking factory-file access. Schema installation and initialization both run twice, followed by login registration and company enrolment. Native PostgreSQL 16 and 18 runs passed (`/tmp/abs-setup-contained16.log` and `/tmp/abs-setup-contained18.log`). They verify final migration checksums, one company credential, zero sessions, and booking still OFF. The only replaced connection boundary is an owned local Unix socket instead of provider TLS; password prompts use synthetic test input. These tests do not claim Windows terminal or hosted/provider acceptance.

This is part of the replacement for the old project-specific control/provisioning scripts. The remaining old privacy, test, backup and hosting commands must be retired or redirected to their reviewed common equivalents before final handover. No old command is considered safe merely because the new website no longer imports its backend.
