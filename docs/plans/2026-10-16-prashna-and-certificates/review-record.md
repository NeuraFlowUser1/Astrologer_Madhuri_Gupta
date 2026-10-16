> Accepted planning snapshot. Planning-stage observations below are historical. See [the current feature guide](../../prashna-kundali.md) for implementation, publication and saved-settings status. Private study files and screenshots remain outside this repository and hosting export.

# Planning review and corrections

16 October 2026. **The plan and private study are ready for the owner's review. Production implementation has not started.**

## Review passes

| Pass | What was examined | Result |
| --- | --- | --- |
| 1. Source and ownership | Canonical versus older dirty checkout; current service configuration; all public entry points; actual booking/controller/settings/receipt and route owners | Scoped work to the real Sarsa worktree and existing booking contract. No new engine, schema, calendar, provider account or separate form. |
| 2. Contract and design critique | Prices, units, count/duration, disabled service, concurrent settings changes, receipt limits, five-card composition, About measurements, artwork/photograph ownership | Corrected the risks listed below; wrote numeric specs and twenty internal execution checkpoints. |
| 3. Rendered desktop/phone critique | Five private views at 1440×900 and390×844; narrow/wide layouts; image crops, title/action fit, fee wrapping, seven proposed opening frames | Corrected cropped vector artwork, a narrow fifth-card image, small-screen fee/button wrapping and clipped opening paper corners. Preserved initial failing study captures for traceability. |
| 4. Re-review and boundaries | Revised views, tabs/FAQ/count interactions, reduced motion, native opening/ambient, documentation links, source fingerprints, export boundaries and legacy references | No further meaningful planning correction found in this bounded pass. Remaining implementation-dependent proof is explicitly listed; this is not a claim that unbuilt production code has no bugs. |

## Issues found and resolved in the plan/study

| Finding | Correction / why it matters |
| --- | --- |
| A fifth ordinary half-width card would leave an orphan | Intentional full-width final row on larger screens; stacked on phones. Original four cards stay in order. |
| About's current identity baseline would count the fifth row and cancel out its new height | Measure the original four identity rows separately, identified by data-service-id; preserve action compensation and natural intro dominance. Remove only certificate height/observation. |
| Adding the catalogue item does not register an enabled booking service | One explicit protected current-revision settings addition, after compatible website publication/readback. No direct database edit or bootstrap overwrite. |
| Backend-first activation could expose the service in the older ambiguous price presentation | Publish compatible UI first; the existing coordinator refuses an unknown/disabled requested ID. Explain that short unavailable state, offer existing policy refresh, then activate once. |
| The static quote_version is already different from live and has no source consumer | Remove the unused informational marketing hash; record the actual returned runtime version in release evidence. No fake hash or second website release for metadata only. |
| Existing shared customer receipt/PDF does not display question count | Record that limit accurately. Make unit/count/total explicit before payment; retain shared receipt/service/agreed-fee behavior. Do not invent receipt fields or derive quantity from a total. |
| A bare ₹1,100 could be mistaken for the whole booking fee | “Per question” appears on directory/booking/detail; count and total are explicit. Native 1–10 selection avoids empty/fractional input states. |
| The generic detail/motion/story components have no Prashna content and can redirect/fall through | Use an explicit Prashna page/art/motion owner; add the new motif/media; do not force a new ID into Numerology's fallback. |
| Combining a photograph's chart/clock with another full SVG over it would duplicate objects | Permanent vector assembly in the hero, primary photograph for service cards and supporting photograph in the method section. No stacked duplicate scene. |
| Initial wide-card SVG used photographic cover cropping and clipped the question note | Study vector uses contain with a matching ground; final photos have their own 20–80% vertical object safety requirement and implementation-time crop review. Initial evidence retained. |
| Flex alignment made the phone fifth-card image narrower than its peers | Explicit stretch and full-width photo wrappers for the new stacked card. |
| A fixed tablet photo height or shallow booking thumbnail would cut the planned photo objects | Preserve Home's existing1240px wide-screen cap. Tablet fifth-card photos use2:1; the new Booking photo uses3:2, with a180×120px desktop stage. Original four thumbnails remain. |
| Phone total label wrapped into three short lines; CTA arrow broke off | At ≤430px put label above amount; deliberately split action from amount/arrow, keeping the latter together, including ₹11,000. |
| Opening paper corners exceeded the stage during the first rotated frame | Scale the opening leaves from .88 to1 while retaining their staged opening/settled positions. The corrected first frame was inspected again. |
| A realistic study's default count differed from the proposed booking default | Default now1; the customer can select3 or10 to inspect totals. |
| The study initially simplified some unchanged Services context without explaining its boundaries | Restored knowledge artwork and final Contact invitation in that view; added per-view toolbar notes explaining excerpts and preserved chapters. |
| Existing legacy booking-visibility.json describes superseded paths | Confirmed no runtime importer; identify it as a retained legacy snapshot, not a second route authority. Do not wire Prashna into it. |
| Current route/certificate checks contain stale expectations | Plan explicit scope-aware corrections while retaining review/private-asset/security protections. No checks run or weakened to make a green result. |
| Client-local plan links would not exist inside the separate website Git root | Future implementation preserves an accepted plan/spec snapshot in repository docs, with source/hash; current guides link to that snapshot and the feature guide. The private viewer/images remain outside hosting export. |

## Motion findings — installed third-party review guidance

| Before / risk | After | Why |
| --- | --- | --- |
| A single generic fade could stand in for “assembly” | Design spec section G defines five overlapping acts across3600ms, followed by a settled hold and separate bounded ambient groups | A reader can see paper open, chart settle, question note arrive and clock dock; existing Home/About movement stays untouched |
| Entrance and ambient could overwrite the same transform | Separate outer entrance and inner ambient wrappers, shown in study.js:88 and study.css:41 | Keeps final docking positions intact and makes interruption predictable |
| Initial leaf rotation clipped meaningful paper corners | .88 starting scale, opening to1, specified in design-spec.md section G and shown in revised first frame | Prevents the crop from masquerading as intentional motion |
| Essential controls might wait for scene completion | Copy/CTAs stay usable; existing focus settles scenes; tab activation settles its new local entrance | Reading/booking does not depend on waiting for decoration |
| Pointer-only or motion-dependent explanation | Native keyboard tabs/disclosures, focus indicators, stable content; reduced-motion final state | Same information remains available with keyboard/system motion preferences |
| Loops might run outside the visible section or over a focused action | Existing owner rules preserved; new ambient visibility/hidden/hover/focus pauses and cleanup specified | Avoids needless work and distracting a reader using the controls |

**Planning verdict: approve for owner review.** The specified new movement has clear purpose, bounded values, separate transform owners and responsive/reduced-motion behavior. This is approval of the proposed design/logic, not an automated code-quality or production-motion pass. Lower-section integration timelines and actual generated-image crops still need to be built and visually reviewed.

## Actual study observations

Machine-readable observations (private client study: `browser-observations.json`) contains **30 view/viewport observations**: five views × six screen sizes, at1440×900,390×844,1920×1080,768×1024,360×800 and320×740. No sideways overflow or failed image was observed in that inventory. This is DOM measurement and visual inspection of a private composition, not a test suite or an actual hosted-product result.

The evidence folder contains **27 screenshots**, including three initial problem captures retained for comparison. Core final screenshots cover all five views on desktop and phone. Targeted captures include tablet About rows, tablet fifth directory card and320px review at10 questions. Seven proposed opening positions are saved at0,450,1100,1750,2300,3100 and3600ms. Captured images were opened for visual review, including the intermediate motion frames and narrow layout details.

Observed interactions:

- Pointer selection displays the Family and relationships examples.
- Keyboard End selects “A decision ahead”.
- Opening another FAQ leaves exactly one open.
- Question choices1/3/10 display ₹1,100 / ₹3,300 / ₹11,000.
- Reduced motion leaves opening progress1.000 and both ambient animation names none.
- Viewer phone frame measures390×844.
- Native opening observation (private client study: `native-motion-observation.json`) reaches progress1.000. After that, the note's real computed translation changed from approximately−.14px to−1.75px over the sampled second, demonstrating the visible ambient loop. This is not a frame-rate/performance measurement.
- Latest browser console read had zero errors/warnings. The initial missing local favicon produced a404; both HTML documents now contain a small inline favicon.

The private viewer is at **http://localhost:8854/** and serves only the study, prior inspection images and selected existing media. It does not serve private configuration, .env, other clients or source archives. It binds127.0.0.1. Nothing is published to the official website.

## Preservation and limits

The canonical application remains clean at **7905f9b582c3712fbc33cb5e6d7ccfaeeba5888e**. All **31 protected file fingerprints** match the investigation record. No source/runtime settings, contained package, database, provider, Git commit, push or deployment was changed. The existing application code was not compiled because this was a planning-only pass.

No test suite, coverage/lint/release gate, private login, booking/payment/enquiry submission, message/email or customer lookup was run. Source inspection found three current automation workflows, none push-triggered; no workflow was dispatched. Owner decisions were recorded as confirmed in the investigation README/JSON, and a narrow planning pointer was added to the enclosing client README so a resumed agent can find this plan. The canonical application's README/source remain unchanged.

Still implementation-dependent:

1. Generate/review the two final Prashna photographs and their six renditions.
2. Build the production components and all six native section timelines; compare to the accepted study and frozen original sections.
3. Apply the About measurement formula to actual root-relative art at both sizes.
4. Read the current full protected settings document and perform the one approved service addition, using actual authentication/access.
5. Compile/publish through the existing route, then observe actual official page/assets/policy/selector results.

These are remaining implementation tasks, not unresolved business choices. No further business information is needed for the present planning scope.
