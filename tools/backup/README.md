# Sarsa encrypted backups

Current owner decision: store encrypted backups in **Sarsa Project 004 – Encrypted Backups**, in the Google Drive owned by **sarsajyotish@gmail.com**. This supersedes the temporary NeuraFlow destination. The backup Desktop client belongs to Google Cloud project `sarsajyotish-backend`; the booking website's Google connection is separate.

Daily GitHub Actions backups are authorised in addition to monitoring. The exact-repository/public-visibility guard preserves the owner's maximum of 100 included minutes/month: a private repository skips the runner. The workflow does not build, release or deploy the website. It is prepared locally and has not been published or activated.

## Archive and restore

The schedule is 03:02 UTC daily (08:32 India). Official PostgreSQL 18 tools are pinned to a reviewed Docker digest, matching the production database major version. Source identity is fixed to Sarsa's direct production host, `neondb`, and `sarsa_booking_backup`. The restricted role reads only `sarsa_booking`, with no schema creation, data modification, privileged membership or booking-function execution. The operational grants include future tables/sequences created by `neondb_owner` in that schema.

`pg_dump` owns the consistent snapshot. Its custom-format output streams immediately into AES-256-GCM encryption. Only encrypted archives are written into a private temporary directory. The archive authenticates project/day/format metadata. Private records, passwords and key values are never printed or uploaded as GitHub artifacts. Connections require full TLS certificate/hostname verification and channel binding, with the installed `/etc/ssl/certs/ca-certificates.crt` trust bundle explicitly selected; a bundled client's unavailable default trust store must not cause TLS verification to be disabled.

Before upload, a full authentication pass precedes restoration in a uniquely owned PostgreSQL container with no network or application workers. The restore uses one transaction, exits on errors, restores constraints and verifies migration checksums against checked-in sources. Cleanup verifies the exact generated ownership label before removing the container and volumes. Production has 19 applied migrations at this checkpoint; local source has 30. Restoration accepts known unchanged migration records, without pretending newer migrations were already applied.

This proves archive/schema/data restoration. A disaster recovery must also preserve application encryption keys, recreate restricted access roles, and reconcile pending provider actions before workers restart. Archive restoration alone does not prove that emails, payments or calendar jobs may be replayed safely.

## Drive storage

The dedicated Google grant requests only `drive.file`. The helper verifies the actual Drive owner and quota. Folder/file metadata identifies Project 004. Resumable upload uses a preallocated file ID; an uncertain response is reconciled against that ID rather than creating a duplicate. Size/checksum transport checks and authenticated download verify the stored encrypted bytes. An existing daily archive is verified and restored instead of duplicated. Ambiguity fails explicitly; sharing settings are not changed.

No retention deletion is authorised or implemented. Successful copies are retained. Insufficient space fails visibly instead of buying storage, deleting archives or changing accounts. Retention and operator response should be reviewed before claiming indefinite unattended coverage. Initial compressed archive ceiling is 512 MiB. GitHub scheduling delays/inactivity and alert delivery still need operational acceptance.

## Protected GitHub settings

- `SARSA_BACKUP_GOOGLE`: dedicated Google permission. Successful owner/quota check and names-only GitHub verification completed. The app was published after a Testing-only 403; publication is owner-reported. Verified free space was 16,103,896,729 bytes on 30 September 2026.
- `SARSA_BACKUP_ENCRYPTION_KEY`: independent canonical base64url 32-byte recovery key. GitHub cannot return a saved secret. An owner-held password-manager copy is required. An unused lost key may be replaced only before the database setting and any workflow exist; used archives require preservation of their original key.
- `SARSA_BACKUP_DATABASE_URL`: restricted direct production connection. The permanent role and password were created after explicit owner approval. The clipboard helper authenticated successfully, verified TLS/identity/read-only permissions and 19 readable migration records, and saved the protected GitHub setting. Names-only verification confirms all three settings exist.

GitHub accepted secret writes despite an `admin=false` permissions summary; do not assume manual saving is required from that summary alone. Automatic review rejected plaintext database credentials in command-input arguments. The safer helper reads a URL copied by the owner into the Windows clipboard, validates identity/TLS/read permissions locally, and sends it to GitHub through a local process pipe. No URL is returned to chat, logged, or stored in a file.

## Local tools and proof

- `authorize.py --client /path/to/client.json`: Google's Desktop loopback approval with state, S256 PKCE and a 15-minute window. Verifies Sarsa ownership and copies the grant to the Windows clipboard. It does not create a folder or upload data.
- `configure-key.py`: creates the recovery key and sends it to GitHub and clipboard. Existing keys are refused by default. `--replace-unused-key` requires explicit operator intent and rejects any published workflow or database setting. `--hold` keeps the generated key only in process memory for 30 minutes; SIGUSR1 copies it again without displaying it.
- `save-database-setting.py`: reads the owner-copied connection from Windows clipboard, verifies the actual restricted login with TLS, and saves only the protected GitHub database setting. `--wait-seconds 900` starts a bounded reader before the owner copies a short-lived connection. Credentials stay inside the local process; errors return only fixed safe categories. `database_setting.py` contains the tested setup behavior.
- `provision-read-role.sql`: reviewed operational role setup outside application schema migrations. Creates no customer records; aborts if the role exists or privileges differ from the specified read scope.
- `check_restore.py`: explicit synthetic offline PostgreSQL 18 dump/encrypt/restore proof; all 30 local migrations and a synthetic row passed. Removes only its own test containers.

Twenty-three backup/setup tests pass: `python -m unittest discover -s tools/backup -p 'test_*.py'`. Install `requirements.txt` for the scheduled job. The local database handoff additionally uses the booking engine's already-installed psycopg dependency, imported only during that setup operation. No paid resource, live email/payment or customer-data upload has been performed in these checks.

Remaining activation evidence: explicit owner confirmation of the saved recovery key, reviewed source publication, first encrypted upload/readback/offline restore, schedule and operator failure-alert proof. Docker is unavailable in this WSL session; the earlier synthetic offline restore proof remains recorded, and the first hosted runner must verify the current pinned image, production archive and restore. Do not claim daily backup coverage from saved secrets alone.

References: [Drive owner/quota](https://developers.google.com/workspace/drive/api/reference/rest/v3/about/get), [resumable uploads](https://developers.google.com/workspace/drive/api/guides/manage-uploads), [Google Testing grants](https://support.google.com/cloud/answer/15549945?hl=en), [desktop approval flow](https://developers.google.com/identity/protocols/oauth2/native-app).
