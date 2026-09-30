# Private development concurrency acceptance

`concurrency.py` is an owner-run check of the actual slot exclusion constraint using two independent database connections. It proves overlapping reservations cannot both persist and adjacent intervals can coexist. It does not claim complete checkout, staff-move, provider, load or payment acceptance.

An automatic approval review rejected sending a privileged connection string through Codex terminal input because it would enter the execution transcript. That attempt was stopped before input or database changes. Do not retry it using an indirect credential transfer. The prepared script instead takes a hidden prompt in the owner's own terminal, outside Codex tool calls. This owner action remains pending.

In Neon, choose `sarsa-jyotish-sansthan` → Connect → branch **booking-development** (`br-still-mud-b38cy2py`) → database **neondb** → role **neondb_owner**. Copy its connection string privately; do not paste it into chat. Production is explicitly rejected by this script.

From the owner's Windows PowerShell, while the existing local Python environment remains available:

```powershell
wsl.exe -d Ubuntu --cd /mnt/d/coding/business/neuraflow-website-factory/03-client-projects/004-sarsa-jyotish-sansthan --exec /tmp/sarsa-booking-venv/bin/python tools/booking-checks/concurrency.py
```

Paste only at the hidden local prompt. The script rejects piped/noninteractive input, all other hosts/databases/users, extra connection overrides and nonstandard ports. It normalises the known development pooler hostname to its direct endpoint, verifies TLS hostname/certificate and requires channel binding. Seven connection-rejection checks and syntax inspection pass; actual independent-session acceptance is not yet claimed.

The check writes only three random synthetic slot-closure IDs at an isolated2035 interval on development, without changing intake, permissions, bookings, payments or notifications. It observes the second connection blocked by the first, commits the first claim, requires a database exclusion error on the overlapping claim, and accepts an adjacent claim. Finally it deletes only its own IDs with its exact marker and no booking association. Time limits bound network, statements and lock waits. No raw connection, password or database exception is printed. A cleanup failure reports only its generated synthetic IDs for manual review; it must never be called a passed test. It makes no production/provider request.

The final `PASS` means constraint contention, adjacent-boundary behaviour and exact-ID cleanup all passed. Share that result wording only. The `/tmp` Python environment is a current-session dependency, not a permanent installation; re-establish the declared project requirements if it is missing after a restart.
