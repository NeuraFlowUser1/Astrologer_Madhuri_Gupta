# Operating/search efficiency patch

Public pages use a 60-second periodic display check, active booking uses five seconds, and hidden/disposed pages start no periodic work. Focus and entry still refresh through the same bounded single-flight controller. This reduces periodic requests; total provider CPU savings require later measurements.

New additive APIs: createStateController serverSnapshot reader and initialDisplay boolean (default false); start third options profile/refreshOnStart; setProfile. An initial public snapshot retains only a display boolean and cannot admit protected work. createReactBindings adds state context/BookingStateProvider(controller) and lifecycleOwner entry/bindings. Ordinary booking clicks await real freshness and discard superseded intentions; modified links keep native behaviour. bindVisibility provides explicit non-React ownership while visibility.js retains automatic compatibility.

createUseEnquiry accepts an optional deterministic public serverSnapshot reader; actual browser storage/controller authority remains separate. Optional booking recovery cannot start from an unverified display-only seed. Previously admitted retained work can survive a bounded freshness check, with its own operations still enforcing current authority.

Generated pages accept exact object metadata and synchronous renderPage complete documents from the application's real components. Both sitemaps list only ordinary public pages; booking utilities retain noindex. TimeField's redundant outer Group is structural only; labelled DateInput/DatePicker behaviour remains intact.

No database migration, permission, caller, provider or payload contract changes are part of this neutral patch. Publish application/worker and release binding together through the existing guarded procedure. Do not infer provider acceptance from a package seal or local build. Clinic-only doctor calendars/payment-review repairs belong to its independently versioned extension.

Release 1.0.1-rc.2 corrects one inherited native test fixture: its contact-correction submission supplies the already required email so the unchanged lost-reply/reconciliation assertions actually execute. No product runtime, database, provider or API bytes differ from rc.1.

Release 1.0.1-rc.3 additionally keeps one authoritative metadata tag when descriptions contain apostrophes/quotes or a page renderer repeats metadata. Native initial pageshow reuses an existing bootstrap attempt; restored/hidden/never-started lifetimes still refresh. Focused regressions preserve fail-closed admission and actual foreground recovery. Inherited native fixtures now serve the extracted visibility module, assert retired code controls are absent, trigger real foreground reads under the approved public cadence, and exercise the current read-only receipt/lookup labels without loosening authority or lost-reply checks.
