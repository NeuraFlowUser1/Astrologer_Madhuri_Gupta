> Accepted planning snapshot. Planning-stage observations below are historical. See [the current feature guide](../../prashna-kundali.md) for implementation, publication and saved-settings status. Private study files and screenshots remain outside this repository and hosting export.

# Prashna Kundali and certificate removal — implementation plan

**Status: approved by the owner; implementation underway on a separate branch.** Date: 16 October 2026. This document authorizes no production action by itself. Planning documents and the isolated layout study are the only current changes.

## 1. Objective and settled decisions

Make Prashna Kundali a complete fifth service in Sarsa, including an informative page and the existing real appointment journey. Remove the four-document certificate section from About Madhuri. Keep the present website's identity, artwork, established movement and unrelated customer journeys.

| Decision | Settled rule |
| --- | --- |
| Service name / ID | Prashna Kundali / prashna-kundali. Use “Prashna Kundali” consistently; familiar “Prashna Kundli” may occur naturally in explanatory copy, never as a second ID. |
| Fee | ₹1,100 per question = 110000 paise. INR. |
| Question count | Whole numbers 1–10. Default 1. Maximum total ₹11,000. |
| Appointment | One 30-minute appointment on Google Meet, independent of question count. This is not Project 001's clinic booking model. |
| Enquiry | Existing Contact flow only. Do not copy Project 003's separate Prashna submission form. |
| Preparation | No additional mandatory birth details, question text, location or upload. Use required_preparation = [] as in Project 003. Existing full-name/phone requirements and email-verification settings continue. |
| Chart timing | Describe the traditional question-time chart. Do not claim that entering notes or making a booking creates a chart, records its astrological moment or sends a question for an advance reading. Bring the question to the appointment. |
| Extra questions | The online booking sells the chosen 1–10 questions in one appointment. Do not add an unapproved extra-payment flow, promise extra time or promise unlimited questions. A later request is handled through the existing Contact journey. |
| Certificates | Remove the entire public gallery, course explanations, document viewer and associated published media. Preserve supplied originals, AI versions, comparison studies and previous source history. Do not move the same education claims elsewhere. |
| Motion | Preserve existing timelines, paths, stage order and unrelated geometry. New Prashna movement has its own scoped owner. No new pause controls or disposable construction lines/dots. Existing system reduced-motion behavior stays. |
| Verification | Respect the owner's current no-tests/no-release-gates boundary. Perform source review, ordinary browser inspection and necessary website compilation; do not run suites, lint/coverage gates or real payment/email/customer actions without later instruction. |

The fee, limit, duration and existing-flow choice were confirmed by the owner after the investigation. No additional business answer is currently needed to finish this plan.

## 2. Evidence and source of truth

Canonical application and Git root: **03-client-projects/004-sarsa-jyotish-sansthan/.local-runtime/about-certifications-20261012**. Current branch: **about-certifications-20261012**. Verified clean source: **7905f9b582c3712fbc33cb5e6d7ccfaeeba5888e**. Recheck before implementation; if it advances, review the actual intervening changes and apply this narrow scope to the latest appropriate source.

The enclosing imported checkout is an older dirty application. Do not build from it, copy it over the canonical source, reset it or bundle its unrelated files. Project 003 is reference-only; its current published reference was GitHub main **4b9d4bac935dba8fee6d61a48517763753e669db**, rather than its older dirty local checkout.

The private inspection register (client design-review/2026-10-16-prashna-and-certificates-inspection/README.md) contains 44 screenshots: 39 Sarsa and five relevant AstroAdvice views. It covers 13 main Sarsa pages plus two access addresses at 1440×900 and 390×844. Its JSON contains protected-source hashes and observed public settings. These are bounded source/visual observations, not fresh provider acceptance or a full-system result.

| Authority | Owns | Does not own |
| --- | --- | --- |
| Saved company business settings | Enabled services, unit fee, maximum questions, duration, preparation and all existing operational settings | Page layout or image crop |
| Public booking-policy response | Current customer-readable projection and quote_version | Permission to overwrite the complete private settings document |
| frontend/src/site/catalogue.json | Static public marketing snapshot generated from the agreed settings values | Checkout authority or a fallback booking engine |
| Existing booking coordinator | Selection, quantity, fresh availability, quote freshness, credentials, recovery and idempotent checkout | New marketing content |
| Client pages/site modules | Appearance, explanatory copy, media, local interaction and the existing API consumer presentation | Server price calculation |
| Project 003 | Relevant service concept and supported per-question behavior | Sarsa's visual design, factual endorsements, accounts or provider configuration |

frontend/src/site/booking-visibility.json is a retained legacy snapshot: the current source search finds its hosting export entry but no runtime import. It is not the route authority and still describes older access paths. Do not copy that obsolete model or add a second route owner for Prashna; project.json, App/routes/metadata and the generated surface manifest own the current route. Its unrelated cleanup is outside this programme.

The contained shared booking release is **54af467afbe152286f1f81f28f904a8b59b51e31111e6a81d93b1d340bd3720a**, 576 manifest files, migrations 001–037. It already supports this service contract. Do not edit its bytes, installation identity, worker, database schema, private access rules or another client.

## 3. Scope: what changes and what stays

| Work area | Exact result | Scope size |
| --- | --- | --- |
| About removal | Remove four certificates, reader and active public media; close the gap while retaining original backdrops | Medium |
| Home | One fifth service card, two relevant FAQ answers and their natural links | Small |
| About service choices | Five service rows and the existing personal paragraph's service list | Small |
| Services | Fifth image-led card and question-guide choice; explicit price basis; natural Prashna explanation | Medium |
| Prashna page | One new page with six sections, distinct imagery, useful question examples, preparation, fees and FAQs | Largest visual item |
| Booking presentation | Fifth enabled radio card, “per question”, native 1–10 selection, quantity/unit/total in review and clear unavailable-service state | Medium |
| Configuration / discovery | One saved service addition, bootstrap alignment, static snapshot, route/metadata/sitemap/asset/export registrations | Medium; operational care required |
| Retirement / documentation | Remove obsolete certificate runtime/check references; align current guides and preserve dated evidence | Medium |

Preserve: all four existing service offerings and amounts; Home hero and Meet section; the combined Home emblem/process chapter; original About opening/approach/personal/invitation choreography; Contact map/address/form; all twelve accepted Reviews and filters/readers; shared header/footer/navigation; name-and-phone booking-details access; payment, confirmation, receipt/PDF, staff permissions and existing cancellation/rescheduling/refund rules.

No new top-level navigation tab is needed: Prashna belongs under Services and in the existing service lists. Do not add a footer service-link collection or a Prashna review filter without actual approved review content.

## 4. Exact booking contract

Append one service record to the **latest saved** services array; retain the original order and exact values of the existing four:

    {
      "id": "prashna-kundali",
      "name": "Prashna Kundali",
      "enabled": true,
      "pricing": {
        "kind": "per_question",
        "amount_paise": 110000,
        "maximum_questions": 10
      },
      "duration_minutes": 30,
      "required_preparation": []
    }

All five services use Madhuri's existing shared schedule. Quantity does not create another calendar, provider resource, slot or concurrent appointment. Existing shared conflict/hold ownership stays unchanged.

Do not replace the settings document with appointment-settings/business-settings.json. The bootstrap file is a source/install record, not proof of the current production document. Preserve saved hours, timezone, horizon, notice, buffers, contact rules, verification toggles, email budgets and operational choices.

Customer flow:

1. A service link opens **/booking?service=prashna-kundali**.
2. The existing coordinator reads the real policy and only selects a matching enabled service.
3. The customer selects 1–10 questions using a native select control; labels are “1 question”, “2 questions”, etc. This avoids empty, fractional or out-of-range number-input states.
4. Editing quantity uses the existing edit/questions action. It invalidates the old slot quote and acknowledgement; availability is read again with service_id, day and questions.
5. Choosing another service resets questions to 1 through the current shared coordinator.
6. The appointment time remains one 30-minute slot. Quantity never multiplies the calendar duration.
7. Existing name, phone, optional notes and current email-verification rules apply. No second question submission is created.
8. Review shows service, question count, unit fee, total, date/time, 30-minute duration and Google Meet. Total uses the fresh server quote when available. The locally calculated number is explanatory only.
9. Existing fresh-policy/fresh-slot/acknowledgement and verification checks gate payment. The server validates service/count/price/quote and owns the booking amount.
10. Saved booking records retain their service/quantity/amount snapshots. Existing receipt, payment recovery, PDF and notification/calendar owners continue unchanged. The current customer receipt/PDF displays service and agreed fee but does not display question count; do not claim that it does, infer count from a fee, or extend that shared contract in this narrow programme. This addition makes quantity/unit/total explicit before payment. Do not rewrite historical bookings.

Required visible examples, derived from the same approved fee: 1 × ₹1,100 = ₹1,100; 3 × ₹1,100 = ₹3,300; 10 × ₹1,100 = ₹11,000. Existing fixed-price services must never show “per question” or a quantity selector.

### Errors and concurrency

- Policy loading: keep the current loading/locking behavior. Do not show a bookable static replacement service list.
- Unknown or disabled requested service: the current coordinator clears selection rather than silently selecting another service. Add a narrow, plain notice in Booking after successful policy loading: “Prashna Kundali is not available for online booking at the moment. Choose another service or contact us.” Show it only while the requested Prashna ID is absent/disabled in a successfully loaded policy, no other service is explicitly selected and no saved receipt is active. Include a “Refresh services” button calling the existing flow.loadPolicy, disabled during its read. If Prashna becomes enabled, remove the notice and let the visitor select its now-visible card; a fresh direct page load preselects it normally. Do not force the query service over an explicit alternative choice or loop background policy requests.
- Successful policy load, explicit alternative selection: remove that notice. Failed load: use the existing error/reload state, not the unavailable-service conclusion.
- A saved receipt takes priority over a query parameter. Never reset or reinterpret an in-progress payment to preselect Prashna.
- Rapid quantity/date changes: retain existing abort controllers, sequence checks and fresh-slot rules. A late response for one question cannot replace the latest three-question quote.
- A changed quote_version clears acknowledgement. The customer reviews updated terms before payment; do not suppress quote_changed to make checkout appear successful.
- No slots: use the current choose-another-date state. Do not claim booking is possible or fabricate available times.
- Offline, unavailable payment or an uncertain previous payment: keep current retry/recovery semantics and credential storage. Never create a second payment automatically.
- On global booking OFF, unknown activation or failed admission, the existing guarded booking route remains unavailable. New general service content remains readable. Never infer ON from the static catalogue.
- No private name/phone/question is put in a URL, local image, analytics event, screenshot, commit or shared doc.

## 5. Source-level change map

All paths below are relative to the canonical application. New filenames are proposed concrete implementation owners, not claims that those files already exist.

| Owner | Planned narrow change |
| --- | --- |
| frontend/src/pages/Home.jsx; frontend/src/site/home.css | Append the fifth card, scope full-width layout by its service class/ID and update only the service-choice and unknown-birth-time FAQ answers. Keep existing four card DOM/order and chapter boundaries. |
| frontend/src/site/home-enhancements.mjs; home-motion.mjs | Review compatibility only. The card attention loop already queries actual cards. Preserve existing formulas/timings; edit only if a demonstrable fifth-card selector assumption is found. |
| frontend/src/pages/About.jsx | Remove certificate import/mount; append the fifth service ID, add data-service-id to the rows for measurement, and add it to the personal service list. Preserve other wording and scene owners. |
| frontend/src/site/about-layout.mjs; about.css | Remove certificate measurement/observation only. Preserve service-action height compensation, resize/font observation and three backdrop variables. Establish the frozen four-row identity baseline described in the design spec. |
| frontend/src/site/about-motion.mjs | Preserve the existing 2925ms stagger. Fifth row uses i=4 and ends at progress .97. Keep hero 7150ms and other original definitions. |
| frontend/src/pages/Services.jsx; frontend/src/site/services.css | Add description, fifth guide choice, price basis and wide fifth-card class. Keep the existing two-card rows, image framing, actions, directory movement and section backgrounds. |
| frontend/src/pages/PrashnaKundali.jsx — new | Six-section page; explicit route rather than passing a new ID through another service's fallback branch. |
| frontend/src/site/prashna-content.mjs — new | Plain explanatory text, three question categories, preparation and FAQ content. Prices/limits/duration are read from the static catalogue, not separately hardcoded here. |
| frontend/src/site/prashna.css — new | Scoped visual rules and responsive states from the design spec; reuse present palette/action tokens and common buttons. |
| frontend/src/site/prashna-motion.mjs — new | New component-scoped scene definitions, reusing mountScenes; bounded ambient ownership with cleanup. No new animation package or global scroll override. |
| frontend/src/site/PrashnaArtwork.jsx — new | Purpose-built reusable SVG with separately addressable paper/chart/note/clock parts. Decorative, no computed horoscope or real time display. |
| frontend/src/site/ServiceArtwork.jsx | Add explicit Prashna variant using the same artwork component/motif. Never fall through to numerology or a birth-chart service's image. |
| frontend/src/site/service-media.json; media/services/ | Add two Prashna masters' metadata and six responsive WebP renditions; retain old entries/files byte-for-byte. Masters live in the client design/assets area, not in the deployed bundle. |
| frontend/src/pages/Booking.jsx; frontend/src/booking/booking.css | Add explicit Prashna symbol/image, unit label, native question selector, quantity summary and narrow unavailable-service notice. Extend only the fifth radio card's arrangement. Do not replace useBooking/controller/transport. |
| frontend/src/site/catalogue.json | Refresh the static projection from the agreed/latest service settings. Keep one flat amount_paise per service; add pricing_kind and maximum_questions to the projection, preserving consumers' current fields. |
| frontend/src/App.jsx | Lazy explicit /services/prashna-kundali route before the generic service-detail route; add Prashna to the Services booking-OFF description. Retain existing guards/metadata/access behavior. |
| frontend/src/site/routes.mjs | Add new known page and service ID to legacy marketing hash migration. Strip unrelated query data as today. |
| frontend/src/site/page-metadata.mjs | Add new page/title/description; update Services description. Keep Reviews and all old canonical addresses. Expected metadata count 15 → 16; main public pages 13 → 14. |
| frontend/scripts/public-pages.mjs | Add Prashna to Services OFF copy. Generation already consumes the metadata map; verify new sitemap and ON/OFF page outputs. No custom parallel route generator. |
| appointment-settings/project.json | Add /services/prashna-kundali as general. Do not loosen /booking, receipts or staff classifications. |
| appointment-settings/business-settings.json | Align bootstrap with the approved service; do not confuse this with the saved-settings operation. |
| appointment-settings/public-assets.json | Remove retired certificate public-file entries. Add only new literal public files if any; bundled WebP/module ownership is generated by existing Vite/manifest tooling. Do not add invented /media/services public paths for src-owned images. |
| appointment-settings/hosting-files.json | Register all new page/art/motion/content/style/source WebP files; remove obsolete certificate runtime/public/check paths that it currently exports. Keep private study/source masters out. |
| frontend/src/pages/PolicyPage.jsx | Remove “No Prashna service is offered…”; explain the approved appointment/fee basis where needed. Preserve other booking policy and existing refund rules. |
| Enclosing client README.md, canonical README.md; docs/public-site-refresh.md; docs/appointment-system-release.md; docs/about-certifications.md; new docs/prashna-kundali.md | Reflect actual implemented and published state after work; link this plan/decisions. Update the enclosing client README active-worktree/commit pointer only when the new application is the actual publication source, keeping the former worktree intact. Mark certificates removed from current site, with retained source evidence. No premature completion or old 105/107 assessment presented as fresh proof. |

### Certificate retirement

Remove from the active application/export:

- frontend/src/site/Certifications.jsx, certificates-content.mjs, certifications.css, certifications-motion.mjs.
- The twelve public certificate preview/full/original files under frontend/public/media/certificates and their ownership entries.
- frontend/public/certificate.webp and its two export/classification entries. A current src/scripts/tests/docs reference search found only its public-assets and hosting-files entries, with no runtime consumer. Repeat that narrow search on the implementation branch to detect intervening use before retirement.
- Dedicated certifications preview, browser/layout/motion/page checks and vitest.certifications.config.mjs, after verifying no retained owner imports them.
- Certificate-only assertions in testimonials-build-check.mjs; retain all twelve-review, general-asset-boundary and private-harness protections. Replace certificate-public-presence assertions with certificate-retirement expectations.

Do not remove React Aria/date/dialog dependencies: booking uses them. Do not edit the lockfile or upgrade packages for this feature. Do not delete original client certificate files or archived studies. Do not serve the archive as a new public folder. Do not hand-delete a working site's output in place; build a fresh deployment output so retired public files are absent from the new deployment.

### Static catalogue ownership

The current static quote_version differs from the live version although the four current fees agree. Keep the snapshot honestly distinct from runtime authority:

- Prepare the five-service projection from the approved latest document, preserving the current public fields.
- After the protected settings save, record the actual returned/live quote_version in the implementation evidence, together with the source commit. Do not claim a pre-save candidate hash is live.
- The current static quote_version has no source consumer outside catalogue.json (confirmed by a reference search). Remove that unused informational field from the marketing projection. Record the actual server-returned quote_version in private release evidence after the saved-settings operation. Never fabricate a pre-save live hash or create a second website release just to update an unused field.
- Prices displayed by Booking always come from the live policy/quote. A future company price change must also refresh affected static marketing copy through the established site update process; this programme does not introduce automatic marketing-policy synchronization.

## 6. Safe publication and saved-settings change

This is the recommended **one website release plus one protected service-settings operation**. Do not switch all booking OFF to add one service.

1. Preserve the verified baseline and create a separate named working branch/worktree for implementation, for example work/prashna-service-and-certificate-removal. Keep all older copies. Put an explicitly frozen snapshot of the accepted plan/design specification in docs/plans/2026-10-16-prashna-and-certificates/ on that branch, recording the client-study source/hash and adapting its internal links. Current-state guides link to that repository snapshot and docs/prashna-kundali.md; do not leave GitHub documentation linking to files outside its Git root. Keep private HTML, screenshots and source masters outside the hosting export.
2. Implement and review the whole compatible website, including its new-service-unavailable state and all existing four-service behavior.
3. Read the latest saved settings using existing authenticated **GET /api/company/settings** and prepare a semantic diff. The only new operational fact is the appended service. Treat the full response as private; do not paste tokens, account identifiers, customer information or full settings into public evidence.
4. Publish the reviewed compatible commit through the existing Git main → Vercel route. Keep Codex's Vercel connection disconnected. The current three GitHub workflows are scheduled/dispatch/backup-completion operations, with no push-triggered test workflow; leave them unchanged and do not dispatch them for this programme. Recheck triggers before the future push. Verify the actual official page/chunk/asset identities; a Git push is not proof of deployment.
5. Until the service is added, the real booking selector still offers only four services. A direct Prashna booking link shows the clear unavailable-service message and existing alternatives/Contact. It cannot silently book Kundli Prediction. This short changeover is intentional; no duplicate feature flag, placeholder policy, extra API cache or shadow route is introduced.
6. Re-read the saved settings immediately before mutation. Submit the complete current document plus the one service through existing **POST /api/company/settings**, using the current revision, one nonzero operation UUID, a meaningful reason, existing session/CSRF and registered company-caller checks. The actual protected endpoint access must be available; do not bypass login using a direct table update.
7. If the revision changed, read the current document, preserve the other actor's changes, review the new semantic diff and use a new operation ID/revision. Never force the stale document. Retry an ambiguous identical operation using the same operation ID/payload; do not create a second operation while its outcome is unknown.
8. The existing transaction validates settings, locks the control row, appends an immutable policy, changes the active version/revision and records the audit. It does not migrate or recalculate old bookings.
9. Read back saved settings and public /api/booking-policy. Confirm exactly five enabled services, approved pricing/limit/duration, and unchanged original four/settings. Verify the actual booking selector and quantity totals using ordinary read-only selections, without submitting.
10. Align bootstrap/current docs and release evidence with the actual saved result. Explain any incomplete provider-dependent evidence honestly.

If website deployment fails, do not enable Prashna. If protected settings access/save is unavailable, complete the code/design/docs and record that exact operational blocker; the unavailable-service state remains truthful. Do not call the service fully bookable, replace it with a Contact payment workaround or connect a different account. If the later approval does not include publication/settings mutation, stop at reviewed local implementation and report that boundary.

### Rollback

Two independent changes have separate return points:

- **Visual-only problem:** deploy a corrective/revert commit from the preserved baseline/branch. First check that the target booking UI can present any newly created Prashna receipts; retain Prashna-aware booking/receipt support if necessary. Never restore a baseline that silently misrepresents live service choices.
- **New service operational problem:** read the latest saved settings and disable only prashna-kundali using the same protected revisioned operation. Keep existing appointments, held payments, immutable policy snapshots and financial/audit history. Do not delete the service or restore the entire old settings document over newer changes.
- **Full return before any Prashna bookings:** disable the service first, verify it cannot accept new requests, then revert the website addition. Preserve original files and branch history. Do not force-push or reset other client work.
- Unknown save/deployment outcome: read back the operation/provider/site state before retrying. No guessed success, repeated payment or destructive cleanup.

## 7. Review and evidence programme

The no-tests instruction is deliberate. These are source/manual browser review items, not permission to start automated test suites or real transactions.

| Review | Concrete evidence / boundary |
| --- | --- |
| Source parity | Compare untouched Home/About/service/Reviews/Contact movement owners and assets to the preserved source hashes; explain every intended delta. |
| Build | Use Node 22 and the committed frontend lockfile, as the current application README requires. Necessary existing npm --prefix frontend run build; record compilation/output generation separately from test proof. Do not install/upgrade packages unless a genuine requirement is found. |
| Desktop / phone | 1440×900 and 390×844 for all changed pages; targeted 1920×1080, 768×1024, 360×800 and 320×740 for the fifth cards, long labels, question selector and About geometry. |
| Motion | Observe real entry clocks and settled state; new Prashna hero at 0/450/1100/1750/2300/3100/3600ms using its study timeline, then native integration frames. Wait ≥7.2s for the original About hero and ≥5.1s for Home's combined chapter before judging final geometry. |
| States | Default, hover, keyboard focus, selected/unselected service, quantity 1/3/10, explicit service switch, responsive reflow, image load/failure, reduced motion and no-JS/static copy where supported. |
| Real policy | Read-only service/price/limit/availability observations after authorized activation. No checkout, payment, email, enquiry or customer lookup. Do not label these provider-acceptance proof. |
| Discovery / boundaries | New route refresh and legacy hash; correct title/canonical/sitemap; new general page exists ON/OFF; booking remains guarded; retired certificate files absent from the new deployment; study/motion controls/source masters not exported. |
| Unchanged journeys | Read-only appearance of Contact, Reviews, old service pages, policies and booking-details entry pages. No private staff/customer interaction required. |

Before completion, search active source/config/docs for certificate imports/anchors/public paths, course names, “four services”, “No Prashna”, and independently written service lists. Classify each match; do not change legitimate four-part chart geometry or dated historical evidence. Check /about#certifications through the existing missing-anchor behavior without adding a fake replacement gallery or a large spacer.

Source review must also address stale checks without pretending they have run: check-public-site.mjs currently hardcodes 12 metadata routes, versus the current 15 and planned 16, and carries an earlier protected visual baseline. Align its assertion with the explicit authoritative route set and this approved change scope; do not disable protected checks. Align certificate-specific checks as described above. Any later automated-test permission can run the focused changed-area checks; full local/hosted suites require a later explicit instruction. No coverage claim is possible from this planning/manual programme.

Keep screenshots of both entering and settled states. Inspect them individually, not merely save them. Use the approved study as a component-by-component reference for new layouts and use the frozen current site for preserved sections. If a study or implementation differs intentionally, record the exact reason and revised spec; do not silently call it identical.

## 8. Twenty internal execution checkpoints

These guide one later approved implementation programme; they are not twenty owner approval requests.

1. Recheck canonical source, Git root, clean/unrelated work and current project rules.
2. Preserve baseline and branch separately; capture untouched-source/media fingerprints.
3. Reconcile the confirmed service contract with latest protected saved settings.
4. Generate and review two purpose-made Prashna compositions; reject clipped/incorrect/repetitive images.
5. Produce the six responsive renditions and complete media metadata/alt/crop ownership.
6. Build explicit Prashna artwork/content/page/motion modules.
7. Register the real general route, metadata, canonical, legacy ID, sitemap and ON/OFF copy.
8. Add the fifth Home card and the two relevant FAQ updates.
9. Add the fifth directory card, question-guide choice and per-question display.
10. Remove the About certificates and add the fifth service row/prose entry.
11. Reconcile About's four-row baseline, fifth-row growth and service-action compensation.
12. Add Booking's image/symbol, count selection, unit/quantity/total review and unavailable-request notice.
13. Retire only obsolete certificate runtime/public/export/check references; preserve originals/history/dependencies.
14. Review loading, failed reads, disabled service, old receipt, stale quote, quantity and service-switch paths.
15. Inspect desktop/phone intermediate and settled visuals; correct alignment/crops/contrast/motion in scope.
16. Re-review the complete diff, asset registrations, unchanged hashes and narrow documentation/check assertions.
17. Compile through the existing website build; correct genuine in-scope build/output problems.
18. Publish the reviewed commit through the already documented route, then confirm actual official assets/pages.
19. Add Prashna through the one protected current-revision settings operation; read back the exact service and original settings.
20. Inspect actual hosted selectors/pages without submissions, align current documentation and report achieved/remaining items separately.

If implementation reveals a material conflict in the contract, dangerous shared change or owner-only access dependency, record exact evidence and ask for that real decision. An ordinary layout issue, stale assertion, failed image or missed source reference is correct-and-continue work.

## 9. Completion conditions and next step

The later work is complete only when:

- Four public certificates and their viewer are removed, with originals preserved and no blank gap/drifting backdrop.
- All five service entry points resolve correctly; the new page has complete copy, imagery, movement and responsive states.
- Booking offers the real enabled Prashna service, 1–10 questions, correct totals and one 30-minute appointment; fixed services remain correct.
- The actual saved policy, bootstrap and marketing presentation agree on the new service; unrelated settings/history remain intact.
- Existing choreography, twelve Reviews, header/footer, Contact map and booking-details access remain.
- New routes/assets are correctly registered, retired active files are absent and private study artifacts stay private.
- The actual official publication is observed and documented, with no unrun test/provider proof implied.

**Recommendation:** approve this single scoped programme, then implement it on the separate branch through publication and the protected service addition. Reusing the existing booking coordinator avoids a second form, duplicated prices at checkout and a new maintenance path. Keeping the fifth card as an intentional full-width addition preserves the approved four-card design and makes five services look deliberate.

## References checked for planning

Current-source evidence, not generic documentation, controls the implementation. Installed guidance used: design-audit (screen/state coverage), redesign-existing-projects (targeted work within the current stack) and review-animations/animate standards (motion purpose, interruptibility, pointer/reduced-motion handling). Their broad restyling/removal suggestions do not override the owner's preservation boundary. The design-audit entrypoint's optional references/audit-template.md is absent locally; its available audit protocol was used instead.

Official documentation checked on 16 October 2026: [React Router Route](https://reactrouter.com/api/components/Route), [Intersection Observer](https://developer.mozilla.org/en-US/docs/Web/API/Intersection_Observer_API), [responsive image attributes](https://developer.mozilla.org/en-US/docs/Web/HTML/Element/img), [prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion). These support explicit routing, viewport observation, reserved image dimensions/srcset and system motion preferences. They do not justify a framework upgrade; the project keeps its existing React/Router/Vite versions.
