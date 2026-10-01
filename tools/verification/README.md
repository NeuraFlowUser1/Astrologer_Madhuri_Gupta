# Sarsa reliability verification

This is the authorised non-design strengthening pass following the October 1 audit. It adds repeatable local checks; it does not add an application-test publication gate or a GitHub build/release workflow. Chrome is the browser scope requested by the owner.

## Coverage objective and boundaries

Measure executable lines and decision branches separately, with a minimum of 90% for each of six independent domains: booking backend, backup helpers, protected worker-setting helpers, customer logic, staff logic and recovery worker/observer. Unexecuted files are included. Report exact scope, exclusions and counts; never average a weak domain into a stronger one or count test code as application coverage.

Python coverage includes every active `backend/booking_engine` module, backup helper and protected worker-setting handoff. JavaScript coverage includes booking/enquiry state, transport, payment launch, React flow hooks/forms, the complete functional Booking page (including its input/receipt decisions), route metadata, all five private staff scripts and the recovery worker/observer. Tests, third-party libraries, CSS, other marketing-page composition, decorative motion, static artwork/copy, the retired legacy backend and design-review prototypes are excluded by purpose. SQL/PLpgSQL and Windows setup helpers do not have a compatible percentage from these collectors: direct database/permission tests and secure handoff checks remain separate evidence, rather than a claimed 90% SQL or PowerShell result. The database uses server-only restricted roles and record-bound functions; it does not implement RLS policies.

## Required verification stories

1. Measure a baseline, add meaningful missing success/failure/retry assertions, and enforce both 90% metrics when the complete local coverage command is requested.
2. Exercise overlapping independent reservations, concurrent workers, stale revisions, interrupted requests and provider recovery in an owned isolated database. Synthetic payment/provider responses never become a production bypass.
3. Review dependency advisories, public assets, request and record-access boundaries. Fix relevant defects and record remaining upstream/provider limitations honestly.
4. Extend archive restoration proof through restricted application access and safe reconciliation. No restored customer data or saved provider identities may cause a real send or charge during a drill.
5. Verify the independent problem signal and its intended notification path. A failed GitHub check alone does not establish inbox notification delivery; do not fabricate a receipt or disrupt the production scheduler to manufacture a failure.

## Test-only dependencies

`tools/verification/requirements.txt` pins coverage.py, the PostgreSQL syntax parser used by the isolated restore runner, and pip-audit. The frontend development manifest pins Vitest, its matching Istanbul collector, JSDOM, Istanbul counter helpers and Playwright Core. Node 24 is the verified local/Vercel toolchain (24.19.0 used for this proof). The coverage dependencies require that supported runtime. Chrome is already installed locally; Playwright Core does not download a browser during website installation.

Istanbul is deliberate: staff scripts execute in separate DOM contexts, so the test adapter explicitly merges their counters into the collector. Each original source path stays in the report; unvisited files remain at zero. `summarize.py` rejects missing/unexpected JavaScript files, omitted Python files, empty domains and any line or branch metric below the threshold. The JSON evidence includes numerators, denominators and source hashes. Native Node tests are not counted twice.

The assert-based native Node tests are reused through a small Vitest adapter that preserves their mock-method behaviour. Their original `node --test` command remains valid. New DOM and React tests execute the production functions/components with synthetic transports and verify user-visible decisions and retry invariants.

The baseline is retained separately from subsequent results. Local generated reports go in `artifacts/` and are ignored by Git. Dated summaries belong in the existing automatic-booking-plan QA directory. Each result must distinguish isolated application/database proof, simulated external responses, actual hosted service status and actual notification delivery.

## Repeat the complete local check

From the actual Sarsa application/Git root, install the declared backend and verification Python requirements into a dedicated virtual environment, and install frontend development dependencies with Node/npm 24. For Chrome, install the browser matched to the pinned Playwright Core version if it is not already present. This setup belongs to the developer's machine; it is not a public endpoint or a Vercel setting.

```sh
python -m pip install -r backend/requirements.txt -r tools/verification/requirements.txt
npm ci --prefix frontend
node frontend/node_modules/playwright-core/cli.js install chromium
python tools/verification/run.py --node "$(command -v node)" --chrome
```

`--chrome` builds the actual frontend, then starts and tears down the real API plus a fresh disposable PostgreSQL container. The browser and API use loopback HTTPS and the restricted database login. Only Google's identity response is synthetic; browser-bound sign-in state, secure cookies, role checks, staff writes, receipt redemption and appointment changes run unchanged. External browser traffic is intercepted; no real payment, permission grant or email is made. Saved database records are checked after the browser assertions. The fixture timeout and failure cleanup target only resources created by that invocation. Do not run two Chrome proofs from the same checkout simultaneously because they share one private artifact handoff.

Without `--chrome`, the runner executes all individual suites, all 26 direct SQL/query groups, independent connections competing for one slot, a 40-request/8-worker reservation burst, abandoned-worker lease fencing, both encrypted restore checks and the six coverage thresholds. It accepts no database URL. Both SQL containers and the offline restore container use the reviewed pinned image and generated synthetic credentials. No existing database is a restore target. Docker and OpenSSL must be available; approved commands may need local network/process permission.

The verified WSL invocation was:

```sh
/tmp/sarsa-booking-venv/bin/python tools/verification/run.py \
  --node /home/anan/.nvm/versions/node/v24.19.0/bin/node --chrome
```

Reports are in `tools/verification/artifacts/`: `python-coverage.json`, `javascript/coverage-summary.json`, `coverage-result.json`, `database-drill.json` and `chrome-proof.json`. A failed command exits unsuccessfully. `chrome-fixture.json` and its synthetic receipt credential are removed after the fixture ends. No operational credential is written there. To run Chrome alone after a build, use `python tools/verification/chrome_check.py --node /absolute/path/to/node`.

## Security and acceptance boundaries

The October 1 dependency pass upgraded the backend and backup encryption library from cryptography 48.0.1 to 50.0.2 after three unique upstream advisories. The affected upstream functions are not Sarsa's exposed encryption path; this is a defensive supported-library update. A clearly labelled public synthetic fixture generated with 48.0.1 proves the replacement still reads the old archive and encrypted Google-grant formats. Never rotate existing operational keys merely to install this update.

Production dependency audits and public-bundle credential-pattern checks are dated evidence, not a perpetual guarantee. Repeat the production npm audit and pip-audit on the complete resolved Python dependency list when reviewing future dependency changes. Keep raw resolution/advisory reports private in ignored artifacts; publish only safe summary counts and relevant advisory identifiers.

The Chrome proof is an application-to-database test with synthetic identity, not a new real-provider payment test. The last real ₹1 booking/reschedule/cancel/refund and Google/Resend acceptance remain in the earlier dated evidence. Actual monitor failure-email receipt is recorded separately. No production outage is caused to manufacture that proof. A 40-request burst establishes bounded contention behaviour, not unlimited capacity or a long-running production-scale load test. Coverage above 90% is not a claim that every bug or combination of outages is accounted for.
