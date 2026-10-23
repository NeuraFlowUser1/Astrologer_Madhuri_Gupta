# Home Vastu — 23 October 2026

The owner approved the reviewed six-chapter Vastu design, implementation, code push/publication through the existing Git-linked route, and subsequent clickable-poster design/presentation. The page is implemented and focused local qualification passes. Live publication is recorded separately after readback; a build alone is not deployment proof.

## Customer experience and content

Vastu is home-only across the detail page, Home card/FAQ, service directory/question guide and route metadata. The hero now says “Your home. A Vastu perspective.” and uses the approved generated cutaway-home illustration. Two existing manual pictures remain with four short topics: Entrance, Rooms, Centre and Openings. Each topic has one corresponding marker on either picture. Three small native diagrams accompany layout, daily-life and priority prompts.

The added lower chapter is “The principles behind the plan.” Its three manually selected views show Vastu Purusha Mandala, Brahmasthan and Pancha Mahabhuta. The 9 × 9 grid has 81 cells; its central highlight covers 3 × 3 cells. Five elements replace the grid with distinct labelled symbols, without implying that their pentagonal positions are compass directions. One short explanation is visible at a time. Hidden measurement copies are excluded from assistive reading. Preparation mentions a north-marked plan where known, photographs and questions, without promising a report, remedy, site visit or outcome.

Terminology was checked against [IGNCA's Vastu course outline](https://ignca.gov.in/hi/divisionss/academic-unit/short-term-certification-course/vastu-shastra/) and the sources recorded in the [principles specification](project-004/2026-10-23-vastu-home/principles-section-spec.md). This is traditional terminology, not a scientific efficacy claim or a new claim about the practitioner's credentials.

## Source and implementation

`ServiceDetail.jsx` retains the original shared Matching/Numerology template and four scene keys. `VastuDetails.jsx` owns the new hero, three topic illustrations and principle selector; `vastu-content.mjs` owns its exact short explanations. `vastu.css` is scoped to those components. `ServiceVisualStory.jsx` keeps decoding, cancellation, retry and cleanup, with Vastu-only four-topic/one-marker behavior; other service counts remain unchanged. The media manifest owns four positions per Vastu image and its captions.

The original scene engine and service ambient owner are unchanged. The Vastu hero uses the existing 3000ms clock: surface 0–1200ms, image 600–2400ms, caption 1900–3000ms. The new definition in `vastu-motion.mjs` joins the same page controller: paper 0–700ms, grid 350–1500ms, plan 900–2200ms, emphasis 1500–2600ms; individual grid lines stagger by 25ms. Selection crossfades last 300ms with cubic-bezier(.2,.7,.2,1). Only opacity and transforms animate. Reduced motion settles immediately; focus/hidden/offscreen suspension and route cleanup retain their existing ownership. No automatic picture or principle switching is added.

The palette remains cream/forest with gold detail. Hero title is 36–58px, story title 30–34px, principle title 30–42px, selected concept 27–30px, body 16–17px. The forest panel uses 28px corners/42px padding on desktop, 24px corners/padding on phone; its diagram/copy columns stack at 800px. The cutaway hero has a reserved 4:3 ratio and three responsive WebPs: 480px/31,920 bytes, 800px/73,924 bytes, 1200px/137,500 bytes. The private generated master is preserved outside deployment; no raster text/QR is part of the website.

## Focused proof

- 51/51 checks pass in six focused test files. All ten changed executable source owners are included, with no exclusions and per-file 90% thresholds. Combined coverage: 100% lines, 98.55% statements, 100% functions, 97.04% branches. Every individual owner exceeds 90% in every metric.
- Targeted lint, production build and generation of twelve ordinary pages in both existing booking display modes pass. Unchanged PDF/font chunks retain the existing size advisory.
- Actual compiled app checked at 320, 390, 768, 1440 and 1920px widths: no horizontal overflow; all principle selections work by keyboard and keep panel height; four topics and forward/back pictures agree. Native entry motion inspected at desktop/phone midpoints and settled states. Ambient light runs when visible and pauses on focus. A blocked image preserves the previous picture; retry recovers after the block is removed.
- Eighteen geometry/font comparisons across 1440×900 and 390×844 match the approved private draft exactly, including hero, story, conversation and added panel. Full-page, three-mode, entry and image-error screenshots were opened and inspected in the enclosing client's dated design-review evidence.
- Existing generated ON/OFF reading/booking contracts are checked without changing a live setting. No real booking, enquiry, payment, mail or provider write is submitted. Complete local and hosted suites are not rerun or claimed by this focused refinement.

The [focused receipt](project-004/2026-10-23-vastu-home/local-verification.json) records source fingerprints and exact local observations. Historical 22 October full-suite/package acceptance remains valid only for its original scope.

## Publication, collateral and recovery

Publication uses this repository's existing Git main → Vercel connection. Codex remains disconnected from the Vercel account. Existing fees, catalogue identities, booking package, all 37 migrations, saved settings, providers and accounts are unchanged. Only ordinary public pages and booking/contact destinations are read after publication.

The separate poster uses the real portrait, approved logo, home-only Vastu wording, all five existing service pages, a genuine encoded QR and controlled text. Client deliverables belong under its media/ folder; editable poster source and proof belong in its dated design-review folder. Creating this poster does not add a public website download or send it to anyone.

Recovery is a normal bounded presentation revert through the same Git route. It needs no migration, saved-setting restoration, old booking-package rollback or removal/reset of prior working copies.
