# Home Vastu — focused page refinement

23 October 2026. Approved implementation plan. The owner subsequently authorized implementation, push/publication and poster creation. Current implementation/proof is owned by `docs/vastu-home-2026-10-23.md`; baseline descriptions below preserve the inspected starting point. This is a bounded refinement of the existing Vastu page, not a new website design or a new consultation product.

## Owner's objective

Remove workplace/commercial positioning from Vastu. Give a prospective home customer enough specific information to recognise what the consultation concerns and feel comfortable choosing it. Replace the weak right-hand hero artwork. Use illustrations and purposeful motion, keep the amount of new content modest, and avoid turning the page into a lesson or a list of promises about the practitioner.

The poster plan (private client review: `../2026-10-23-clickable-poster/poster-plan.md`) already uses home-only Vastu wording. Poster production follows the website publication in the same owner-approved programme.

The owner's further instruction keeps the upper half and deepens the lower half through one illustrated principles chapter. The [principles specification](principles-section-spec.md) owns its exact copy, research, geometry and motion; the private draft now includes it. The earlier five-chapter prototype is preserved in the source checkpoint (private client review: `review-history/2026-10-23-before-principles/preservation.json`).

## Actual baseline and source ownership

Inspected baseline Git/application: the client's `.local-runtime/operating-search-efficiency-20261022/` copy. Current implementation is in its separate `.local-runtime/vastu-home-poster-20261023/` copy. Inspected branch `work/operating-search-efficiency-20261022` was clean before this study. The register identifies published runtime `3355508c0c3f796324cd3743598617c95f96d736`; later documentation closeout does not change that runtime.

Live page inspected: <https://www.sarsajyotishsansthan.com/services/vastu-consultation>. Baseline captures are desktop (private client review: `evidence/current-vastu-desktop.png`) and phone (private client review: `evidence/current-vastu-phone.png`). Each scene was scrolled into view and allowed to settle before capture; an unvisited scroll-reveal section must not be mistaken for missing content.

| Owner in the maintained application | Relevant responsibility |
| --- | --- |
| `frontend/src/pages/ServiceDetail.jsx` | Shared Matching/Vastu/Numerology composition, Vastu-specific copy and the wall/floor/house-symbol hero. |
| `frontend/src/site/service-motion.mjs` | One service scene owner: 3000ms hero, 2200ms conversation/preparation/booking scenes; Vastu-specific hero branch. |
| `frontend/src/site/ServiceVisualStory.jsx` | Existing two-picture manual viewer, topic state, selected marker, decode-before-swap, retry, cancellation and cleanup. |
| `frontend/src/site/service-visual-content.mjs` | Existing Vastu descriptions: Space, Directions and Your layout. |
| `frontend/src/site/service-media.json` and `ServiceMedia.jsx` | Two existing illustrative Vastu pictures, responsive files, alt text, crop and marker positions. |
| `frontend/src/site/service-visual-motion.mjs` | Existing 2600ms picture/markers/copy entrance and restrained ambient sunlight; pauses during hidden/offscreen/focused interaction. |
| `frontend/src/site/services.css`, `service-visual.css`, `scenes.mjs` | Existing visual language, responsive layouts, shared animation lifecycle and reduced-motion handling. |
| `frontend/src/pages/Home.jsx`, `Services.jsx` | Vastu card, Home FAQ, directory description and service-choice wording currently mention home/workplace. |
| `frontend/src/site/page-metadata.mjs` | Vastu description currently mentions home/workspace; owns metadata and structured-page descriptions. |
| `frontend/src/site/catalogue.json`, existing BookingProduct components | Marketing facts, existing booking handoff and ON/OFF rendering. Saved protected policy/server quotes remain authoritative. |

Current page has five chapters: hero, two-picture story, conversation topics, preparation and booking. The current hero is two flat CSS planes and a house glyph. Its wording is generic; several paragraphs repeat that a space has a layout and questions can be discussed without showing concrete considerations.

## Research: what the owner needs to know

Vastu is a traditional Indian approach to buildings and spatial arrangement. Its subject matter includes orientation/directions, a planning grid, elements, proportion and the building/site context. This is background for the proposal, not a syllabus to paste onto the customer page. [IGNCA's Vastu course outline](https://ignca.gov.in/hi/divisionss/academic-unit/short-term-certification-course/vastu-shastra/) documents that traditional scope.

An actual residential plan-review service describes entrance direction and door position as separate considerations, then room placement, water points, stairs and the plan's centre. It also considers plot shape and surroundings where relevant. [Practitioner source](https://divyamvastu.com/services/vastu-floor-plan-review). This establishes common consultation topics; it does not prove Madhuri provides that provider's written reports, follow-ups, instruments, visits or methods.

Translate that subject matter into four compact home-facing groups:

1. **Facing and entrance:** orientation of the home and where its main entrance sits.
2. **Rooms and placement:** kitchen, bedrooms, bathrooms and puja space in relation to the overall plan.
3. **Centre and movement:** shape/centre of the plan, connections between rooms, stairs and large fixed features.
4. **Water, light and openings:** water points/storage and the openings, daylight and airflow that give practical context to the home.

The fourth group is a design/editorial grouping, not a claim that these are the only or universally agreed Vastu categories. Avoid prescribing a universally correct room direction, diagnosing a house from an illustration, calling the service scientifically proven, or attributing a specific practice/report to Madhuri without confirmation. No plot/soil survey, vastu score, dowsing, energy instrument, structural remedy, guaranteed result or on-site service is added.

## Selected design direction

### Design intent

Make the hero immediately recognisable as a home-layout consultation. Let the middle of the page show that concrete features are considered together. Keep the existing forest/cream identity, all five original chapters, real booking actions and the two manually chosen story pictures. Add one illustrated principles chapter lower down, before preparation, to give the reader a deeper traditional framework. The customer should be able to recognise their own rooms and questions without studying technical rules.

### Replacement hero

Use the new home-cutaway concept (private client review: `assets/vastu-home-cutaway-hero-concept.png`): a materially believable, roof-open residential model with rooms, doors and windows, photographed on pale paper beside a compass. It is illustrative, not a photograph of a customer property, a practitioner office or an approved/ideal directional plan. No generated labels, dimensions, map measurements or claims are built into the artwork.

Generated with built-in `image_gen.imagegen`. The untouched generated original is retained; its copied master and provenance live under `assets/`. Prompt is recorded in the image brief (private client review: `assets/hero-image-brief.md`).

### Proposed customer copy

Hero title:

> Your home.
> A Vastu perspective.

Hero introduction:

> Vastu is an Indian tradition concerned with the directions, layout and arrangement of a home. Bring your questions about its entrance, rooms and the way you live in it.

Keep the current catalogue-derived ₹4,500 / 30 minutes / Google Meet facts and existing `/booking?service=vastu-consultation` handoff. Do not hard-code the private preview's snapshot fee into a new production component.

Existing picture story becomes **A closer look at your home**, with four manually selected topic choices. Display one short explanation at a time, with an appropriate selected marker/highlight on the illustration:

| Choice | Heading | Copy |
| --- | --- | --- |
| Entrance | Facing and entrance. | The direction your home faces and the position of its main door are different details. Both can be considered alongside the complete layout. |
| Rooms | Rooms in relation to one another. | Kitchens, bedrooms, bathrooms and a puja space have different uses. Vastu considers their placement and directions as part of the whole home. |
| Centre | The plan as a whole. | The shape and centre of the plan, room connections, stairs and large fixed features give context to the arrangement of your home. |
| Openings | Water, light and openings. | Water points and storage, windows, daylight and ventilation add context to the plan, together with the home's immediate surroundings. |

Keep topic highlights honest: a marker points only to a relevant visible feature; do not label an arbitrary courtyard as a kitchen or a model as the customer's measured plan. On a small photograph, one clear active marker is preferable to overlapping circles. Keyboard and touch must expose the same selected state and explanatory copy.

Replace the generic conversation cards with three short, illustrated prompts:

- **Your layout:** The rooms, entrance and fixed features you want to discuss.
- **Your daily life:** Where your family sleeps, cooks, prays and spends time together.
- **Your priorities:** What concerns you, what is fixed and what you are considering changing.

Preparation:

> If you have a floor plan, keep it ready with the north direction marked where known. A few clear photographs and your main questions can also help. Ask the practice what will be useful before your appointment.

Keep the existing availability-aware booking/preparation explanation and contact link. Preparation is guidance, not an additional required booking field or a promise of a written report.

The page keeps the five original chapters and adds one principles chapter, for six overall. The new chapter introduces Vastu Purusha Mandala, padas, Brahmasthan and Pancha Mahabhuta through three manually selected illustrated views. Its exact content and diagram states are in the [principles specification](principles-section-spec.md). Current default main content is **342 visible words**, of which **80** are in the added chapter, compared with **262** in the prior private draft and **212** on the unchanged public page. The changing explanations remain short; no long FAQ, rule catalogue or new case-study claim is added.

## Numeric implementation spec

### Appearance and layout

- Preserve existing paper `#F7F5EF`, forest `#26483D`, ink `#21392F`, pale sage `#E9ECE2`, sage `#9DA996` and restrained gold `#A6814D`. No global palette/type replacement.
- Existing Georgia titles and system sans-serif body remain. Hero **48–58px desktop, 34–40px phone**; section titles **32–42px desktop, 28–32px phone**; body **17–18px desktop, 16–17px phone**, line height **1.55–1.65**; topic/action labels **14–16px** with at least **44px** touch height.
- Maintain the actual `1200px` source container, `48px` desktop gutters and existing narrow gutters. Hero retains the two-column desktop / one-column phone structure; keep photo and text readable around 768px rather than forcing narrow columns.
- Hero image area approximately **480–520 × 360–410px** on desktop, full available width at **4:3** on phone. Corners **24–28px desktop, 20px phone**. Preserve the complete room model in the crop; no stretched or clipped house/compass. Reserve image dimensions before decoding.
- Story keeps the source's desktop `1.3fr / 1fr` arrangement, `40px` gap and one-column phone flow at the existing **700px** story breakpoint. Four topic buttons wrap cleanly with a minimum 44px height. There is no auto-advancing carousel.
- Retain the existing two images, Previous/Next behaviour and measured copy-height reserve. A Vastu-only fourth topic must not change the content/card counts of other services.
- Add the lower forest/ivory principles composition through a dedicated component; its scoped colours, responsive layout and exact artwork are defined in the [principles specification](principles-section-spec.md). The upper section HTML, existing private stylesheet and measured upper geometry remain unchanged.
- Existing conversation/preparation entrance layers remain; add simple meaningful plan/room/opening motifs within those existing areas. No extra floating dashboard, score, diagram legend or fabricated inspection report.

### Motion and states

- Vastu hero retains the **3000ms** source scene clock. Replace its three wall/floor/glyph stages with a coherent support-plane → home-image → finishing-detail arrival, within that same clock. Do not leave the old plane transforms applied to the new image.
- Suggested stage intervals on that clock: support surface **0–1200ms**, image **600–2400ms**, finishing detail/caption **1900–3000ms**. Image movement capped at **24px** vertical and scale **0.98 → 1**. No rotation that makes the actual model hard to read.
- Keep the current **2600ms** story reveal: picture **0–1200ms**, highlight **600–1800ms**, copy/controls **1200–2600ms**. Preserve the **240ms** decoded-image crossfade and the existing three **2200ms** lower scenes.
- The added principles chapter uses its own **2600ms** definition in that same scene owner. The paper arrives, the grid builds line by line, and the plan/emphasis settles. Three diagram modes transition in **300ms** and stay static for reading; no new loop or autoplay is introduced. See the [precise specification](principles-section-spec.md).
- Reuse the current scene engine's smoothstep phases and existing action easing `cubic-bezier(.2,.7,.2,1)`. Do not install another motion library or give the same element two transform owners.
- A new topic highlight/copy change may use **180–220ms** opacity/colour transition; maintain stable height and focus. Reading text does not drift, rotate or loop. No autoplay topic changes.
- Existing ambient sunlight may remain at its source **16000ms** cycle only when visible/settled, with hidden-tab/offscreen/focus/pointer suspension and cleanup. No additional background loop is needed.
- With reduced motion, show settled content and remove spatial travel/ambient animation; allow only a short nonessential crossfade if compatible with existing behaviour. Keyboard focus must reveal readable settled content immediately.
- Image failure retains useful text and a stable illustration fallback; photo switching keeps the last decoded picture while a new request loads and preserves retry/stale-request protection.

Private prototype controls such as replay and animation scrubbing sit outside the customer-like composition; they do not become public pause controls.

## Scope, dependencies and ordinary implementation sequence

1. Review the private visual proposal (private client review: `preview/index.html`), its copy, hero image and motion with the owner. It is a design artefact, not a second hosted website or a second product path.
2. After the exact direction is approved, preserve the affected source baseline, then implement the Vastu-specific content/art branch. Prefer a small dedicated Vastu content owner and a scoped artwork/style owner where this keeps the shared service template straightforward; avoid splitting unrelated service code or creating a duplicate page/router.
3. Keep existing viewer and animation lifecycle ownership. Add the Vastu-only fourth topic and appropriate highlights through the existing contract, without weakening image failure handling or changing Matching/Prediction/Numerology behaviour.
   Add the principles chapter through a small Vastu-only component/content/style owner and register its scene with the same controller. Preserve the upper hero/story; do not transplant the standalone private draft into the app as a second page/router.
4. Remove home/workplace and home/workspace Vastu positioning from the Vastu page, story, Home Vastu card, Home service-choice FAQ, Services Vastu description/question guide and Vastu metadata. Current About's general career/work wording is unrelated and stays. Keep legitimate media provenance that says an illustration is not an office photograph; it is not a commercial service claim.
5. Keep the source-rendered HTML and both ON/OFF public modes aligned through the current build. The same metadata owner supplies accurate home-only descriptions; no alternate URL, canonical or booking route is introduced.
6. Add optimised image renditions through current Vite-owned asset classification. Target responsive 480/800/1200px files, approximately **≤220KB** per largest website rendition and **≤140KB** for the phone-target rendition where visually achievable. Inspect the decoded result before choosing compression. The generated PNG master stays in the private study.
7. Review the complete change for shared-template regressions, text/metadata drift, inaccessible controls, cropping/overflow, stale callbacks and duplicate transform owners. Correct and re-review until clean.
8. Run focused tests, targeted lint and the required production build; inspect actual desktop/phone/intermediate-motion renders. Align the maintained public-site guide and outer client status with what was actually implemented.
9. Commit/push/deployment and read-only public readback require owner authorisation for that complete release programme. If included in the approval, continue through those stages without another internal checkpoint. Full local/hosted suites require their own explicit scope; no real booking/payment/enquiry is needed for this presentation change.

## Shared contracts and exclusions

No fee, duration, service ID, appointment policy, availability switch, customer record, API payload, authentication/permission, database/migration, payment, email, calendar, worker, provider account or sealed booking-package file changes. No added analytics, external tracking, contact form or product fallback. Frontend assets are project-owned; no factory runtime import. Existing supported booking admission still determines visible/available actions.

Retain current Sarsa logo/header/footer, Home/About identity, confirmed studies/15+, 12 approved Reviews, all unrelated artwork/motion and retired-certificate boundaries. Preserve old worktrees and unrelated changes.

## Focused verification and acceptance

- Home-only text is consistent on the relevant page/card/FAQ/directory/metadata; unrelated career questions and historical illustration provenance remain correct.
- All five existing chapters and booking/contact links remain; Vastu ID and catalogue/live fee handling are unchanged. Check both current ON and OFF render contracts without changing a saved live setting.
- Four topic controls, selected text and highlight agree on both pictures. Test rapid topic/photo changes, keyboard focus, first/last image buttons, slow/failing image and route unmount. Other services keep their original topic/marker/media counts.
- All three lower principles modes change the correct diagram, accessible label, caption and explanation without moving the controls or following content. Check the 9 × 9 study grid, its central 3 × 3 highlight, removal of cardinal labels in the five-element view, line assembly, rapid switching, keyboard focus, reduced motion and disposal. Compare preserved upper source/geometry with its checkpoint.
- Check 1440×900 and 390×844 as primary viewports, plus 320px, 700/701px, 768px and 1920px widths where the changed layout warrants it. Inspect default, hover, focus, selected, loading/error, reduced motion and intermediate/settled entries. No horizontal overflow or content hidden by the private review frame.
- Existing focused families include `restored-pages.test.jsx`, `refinement-pages.test.jsx`, current service-visual/media lifecycle tests and metadata/build contracts. Select only affected tests after tracing their actual configuration. Maintain ≥90% measured coverage for changed working code with no exclusion/threshold manipulation; no production-source coverage claim comes from the standalone preview.
- Build-derived HTML, responsive files and any asset classification use the existing pipeline. A passing build does not replace visual inspection or prove publication.
- After an authorised release, compare actual public Home Vastu entry, Services entry and Vastu page with the approved draft and open the booking/contact links without submitting real data.

## Recovery and review decisions

Private review can be discarded without affecting the live site. Source recovery is a bounded revert of only this presentation change; there is no data migration to reverse. Keep original generated and baseline files for comparison; do not reset a dirty checkout, delete a prior worktree or restore old booking packages.

Review pass 1 selected specific home features instead of more generic reassurance. Pass 2 kept the existing five chapters and two-picture interaction rather than adding a long educational section. Pass 3 checked shared-template callers, source-rendered copy, booking modes and the home-only consistency edits. The owner approved implementation, code push/publication through the existing Git route, and subsequent poster design/presentation on 23 October. Focused checks, build and read-only live comparison are included; complete local/hosted suites and real customer/provider writes are not part of this refinement.
