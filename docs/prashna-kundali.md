# Prashna Kundali and certificate removal

16 October 2026. The owner approved the complete [implementation plan](plans/2026-10-16-prashna-and-certificates/implementation-plan.md) and [design specification](plans/2026-10-16-prashna-and-certificates/design-spec.md). Implementation branches from preserved source `7905f9b582c3712fbc33cb5e6d7ccfaeeba5888e`, using `work/prashna-service-and-certificate-removal` in the separate client worktree `.local-runtime/prashna-service-20261016`. Earlier copies and supplied originals remain intact.

## Current feature and activation boundary

Prashna is the fifth marketing service on Home, About and Services, with its own six-section page at `/services/prashna-kundali`. Booking understands its per-question choice, count and fee summary. The four-document certificate gallery, enlarged reader, course descriptions and thirteen active public certificate files are removed. No replacement education claims are inserted.

**Saved-service activation requires the existing company sign-in.** The available browser returned HTTP 401 from `GET /api/company/settings`; the password is owner-held separately from encrypted provider settings. No reset, direct database write, alternate account or replacement settings document was used. Public policy currently offers the original four services. Until the protected addition is completed, `/booking?service=prashna-kundali` shows an unavailable notice and leaves the service unselected. Deliberately choosing another service removes it. Existing booking remains ON.

Website implementation/publication and protected activation are separate completion facts. Do not call the fifth service fully bookable until saved settings and the actual public selector are read back. The new unavailable notice separates its two bold actions by a 20px gap and lets them wrap on narrow phones, with at least 44px tap height. Actual publication identities and read-only observations belong to client `design-review/2026-10-16-prashna-implementation/`, outside this Git root. A push alone does not prove publication.

## Agreed service contract

| Field | Value |
| --- | --- |
| ID / name | `prashna-kundali` / Prashna Kundali |
| Price | `pricing.kind: per_question`, `amount_paise: 110000` — ₹1,100 per question |
| Count | Whole numbers 1–10, default 1 |
| Appointment | One 30-minute Google Meet appointment, independent of question count |
| Preparation | `required_preparation: []`; no mandatory birth details, uploads or separate question form |
| Entry points | Existing `/booking?service=prashna-kundali` and `/contact` |
| Totals | 1 question ₹1,100; 3 questions ₹3,300; 10 questions ₹11,000 |

Existing four services, amounts, shared schedule, contact requirements, verification, cancellation/rescheduling/refunds and stored history remain. Phone is required; email follows the current email-code setting. Quantity does not create another calendar or extend the appointment. The bootstrap records the agreed addition; it must not overwrite the latest saved document. `catalogue.json` is the marketing projection, with its unused stale `quote_version` removed. Actual Booking uses live policy/availability/server quotes. Future fee changes still require aligning marketing through the website update process.

## Presentation and source owners

`PrashnaKundali.jsx` owns six chapters, keyboard tabs and single-open FAQs. `prashna-content.mjs` contains explanations. `PrashnaArtwork.jsx` gives each SVG instance unique definition IDs. `prashna-motion.mjs` reuses `mountScenes`; `prashna.css` owns the new responsive rules. No new font, library, dependency or global scroller is introduced. Seven stale hosting-index entries for already absent legacy components are removed, and 43 existing runtime/media dependencies omitted by the older index are registered. The complete client source/public file lists now resolve to actual files; these registration repairs do not change those existing assets or components.

The 3,600ms hero opens paper leaves, settles a chart, brings in a question note, docks the clock, then holds. Separate inner groups provide 8s/12s note/clock loops, paused offscreen, in hidden tabs, on hover/focus and with reduced motion. Other new chapters use 2,800/2,400/2,400/1,800/600ms entries. Tabs settle their entry before changing content; keyboard changes are immediate and pointer fade lasts at most 180ms, cancelling/retargeting previous motion. No motion controls or disposable construction lines/dots are added. The new page clips horizontal paint overflow so waiting rotated comparison pieces cannot widen a phone page; final content and motion paths remain intact. The first live 390px read exposed 7px before the lower section entered, which prompted this bounded correction.

Two purpose-made AI photographs have six responsive WebPs. The primary was revised after crop review; it appears in service cards. The supporting photo appears once in the comparison chapter. The hero uses permanent vector assembly, avoiding duplicate chart/clock objects over a photograph. Masters, prompts/provenance and private screenshots stay outside deployment. Existing 24 service WebPs remain byte-for-byte unchanged. The five-card 960px set is **634,256 bytes** against a 700,000-byte target; all six new renditions meet their individual budgets.

The fifth Home/directory card spans a complete row. At 651–899px it stacks with a2:1 photograph; phones use 190px card photos. Booking uses a 180×120px image above 650px and a full-width3:2 image below. Original four cards/thumbnails remain. The native count selector uses the configured maximum; review shows count × unit fee and the server-quoted total. Narrow phones put the total label above its amount and give the payment action a deliberate two-line layout.

About removes certificate height from backdrop compensation. Its identity baseline measures only the original four rows, while the actual five-row list supplies growth. Original backdrop/movement formulas and four row timings remain. The fifth row finishes within the existing 2,925ms stagger. Old `/about#certifications` uses bounded missing-anchor handling; no replacement gallery or spacer is created.

## Protected activation and recovery

After independently observing the compatible website on the official domain, use the existing password-backed company sign-in. Read the latest settings/revision. Append only the agreed service through **POST `/api/company/settings`**, with a nonzero operation UUID, reason and existing session/CSRF. The current company UI edits existing rows but has no add-service control, so this approved addition uses the same protected endpoint directly. It does not create a second product or staff journey.

A stale revision requires a fresh read/merge preserving other changes, with a new operation ID. An ambiguous identical operation keeps its ID/payload and is read back before another mutation. Confirm five enabled services, unchanged old settings and actual count/fee totals without submitting payment. Record the returned live `quote_version` privately; no second website release is needed merely to store an unused marketing hash.

Disable only the new service through the same revisioned operation if needed; retain appointments, holds, payments, immutable policy and audit history. Visual recovery uses a normal corrective/revert commit, retaining Prashna-aware presentation if bookings already exist. Never restore an old complete settings document, force-push or delete earlier copies.

## Review and proof limits

The owner retained **no tests or release gates**. Node22 website compilation and ordinary browser inspection are separate evidence. No suite, lint/coverage/preflight command, GitHub Actions dispatch, booking/payment/enquiry submission, email or customer lookup was performed. Existing check source is aligned with 16 metadata routes and certificate retirement; settings exceptions permit only the agreed append/classification/export change.

Actual desktop/phone renders are compared with the approved private study and preserved pages. Native hero stages, ambient hover pause, keyboard topics, single-open FAQs, About growth and unavailable-service switching are observed. Targeted narrow/wide layouts and publication identities are retained in the client execution record. These do not claim a full release gate, coverage, provider/payment acceptance, physical-device or Safari proof. The shared receipt/PDF still displays service and agreed fee without question count; this programme does not invent new receipt fields or change the contained system.
