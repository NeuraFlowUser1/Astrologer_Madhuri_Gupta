# Private development concurrency acceptance

`concurrency.py` is an owner-run check of the actual slot exclusion constraint using two independent database connections. It proves overlapping reservations cannot both persist and adjacent intervals can coexist. It does not claim complete checkout, staff-move, provider, load or payment acceptance.

An automatic approval review rejected sending a privileged connection string through Codex terminal input because it would enter the execution transcript. That attempt was stopped before input or database changes. Do not retry it using an indirect credential transfer. The prepared script instead takes a hidden prompt in the owner's own terminal, outside Codex tool calls. The owner reports that this action passed on30 September2026. A subsequent independent read of the pinned development branch found zero remaining synthetic rows with the exact test marker. Codex did not receive the password or directly observe the hidden-terminal output.

In Neon, choose `sarsa-jyotish-sansthan` → Connect → branch **booking-development** (`br-still-mud-b38cy2py`) → database **neondb** → role **neondb_owner**. Copy its connection string privately; do not paste it into chat. Production is explicitly rejected by this script.

From the owner's Windows PowerShell, while the existing local Python environment remains available:

```powershell
wsl.exe -d Ubuntu --cd /mnt/d/coding/business/neuraflow-website-factory/03-client-projects/004-sarsa-jyotish-sansthan --exec /tmp/sarsa-booking-venv/bin/python tools/booking-checks/concurrency.py
```

Paste only at the hidden local prompt. The script rejects piped/noninteractive input, all other hosts/databases/users, extra connection overrides and nonstandard ports. It normalises the known development pooler hostname to its direct endpoint, verifies TLS hostname/certificate and requires channel binding. Seven connection-rejection checks and syntax inspection pass; independent-session execution is accepted as owner-reported, with separate database cleanup verification.

The check writes only three random synthetic slot-closure IDs at an isolated2035 interval on development, without changing intake, permissions, bookings, payments or notifications. It observes the second connection blocked by the first, commits the first claim, requires a database exclusion error on the overlapping claim, and accepts an adjacent claim. Finally it deletes only its own IDs with its exact marker and no booking association. Time limits bound network, statements and lock waits. No raw connection, password or database exception is printed. A cleanup failure reports only its generated synthetic IDs for manual review; it must never be called a passed test. It makes no production/provider request.

The final `PASS` means constraint contention, adjacent-boundary behaviour and exact-ID cleanup all passed. Share that result wording only. The `/tmp` Python environment is a current-session dependency, not a permanent installation; re-establish the declared project requirements if it is missing after a restart.


## Authorised synthetic support acceptance — 30 September 2026

`support_journeys.py` is an internal test fixture, not a production application mode. It refuses all databases except the positively identified owned local container on127.0.0.1:25434. Temporary credentials stay in private `/tmp` files. Bootstrap all checked migrations in that isolated database, create two clearly synthetic confirmed appointments with synthetic payment evidence, and run the actual HTTP application. The fixture substitutes only Google's external identity response; browser-bound attempts, private sessions, SQL actions and public receipt redemption run normally. `backend/booking_engine/tests/support-journeys-browser.js` drives the rendered staff and customer interfaces.

Accepted: receipt replacement, corrected email/mobile, code redemption, old-access rejection, preserved appointment/payment/slot, two saved staff actions and closing/reopening unavailable time. `verify` checks committed records. `deliveries` uses the actual durable consumers and restricted application role; captured Google/Resend responses prove the corrected meeting, previous meeting removal, independently owned record copies, three messages and idle duplicate prevention. Four Google jobs finish as delivered; three emails finish as provider-accepted, which does not imply inbox delivery. No production bypass, real payment, phone call, Google consent, meeting or message is created. Real customers retain the existing staff verification requirements.

The approved expiry function also passed an isolated rollback check: bounded500-row batches, foreign-key preservation, fresh/in-grace records, repeated idle cleanup and absence of broad application-role DELETE privileges. Cleanup removes only its exact owned test resources when verification finishes.
