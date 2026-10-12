# About Madhuri: studies and certificates

12 October 2026. The owner authorized designing, reviewing, implementing and publishing this additive About section, with the preferred AI-cleaned presentation. The reviewed plan and original/AI comparison are in the client study at `design-review/2026-10-12-about-certifications/` and `design-review/2026-10-12-certificate-cleanup/`. The website implementation lives in the isolated `about-certifications-20261012` worktree; the earlier dirty checkout is preserved.

## Content and appearance

The section follows the personal introduction and precedes service choices. “Her studies and certificates” explains the four supplied courses directly. Two portrait documents precede two landscape documents, with issuer, supplied date/session and one short explanation. It introduces no university degree, accreditation, experience, ranking or outcome claim.

| Supplied evidence | Public description |
| --- | --- |
| Shri Vedang Jyotish Sansthan, Jyotish Shastri | 2010–11 course; certificate dated 31 July 2011. Study in traditional Indian astrology. |
| Same issuer, Jyotish Acharya | 2011–12 course; certificate dated 23 August 2012. Further study following the earlier course. |
| Yogrishi Astro Research Institute | Bhrigu Nandi Nadi Astrology; certificate dated 5 September 2022. |
| Trinity Vaastu / Saarthi Sahil Jain | Two-day online Basic Numerology Foundation Session. No year invented. |

The Hindi documents retain the supplied Madhuri Khandelwal name. The English certificates use Madhuri Gupta. No certificate is renamed internally to imply a different recipient. The earlier yellow AI candidate incorrectly said Bhagya; a new source-referenced edit restores **Bhrigu Nandi Nadi Astrology** before publication. AI presentation can redraw fine strokes/signatures, so originals remain accessible and the cleaned documents are not claimed to be pixel-identical scans. No original input was edited.

Warm paper `#f1ecdf`, forest `#26483d`, sage frames, Georgia headings and the current system body font match About. The section uses 42px/34px/30px headings, 27px/25px/23px course titles, 16–17px explanations, 22px rounded previews and a 1200px content limit. Two columns become one below 800px. Every certificate is contained in full.

## Ownership and interactions

`Certifications.jsx` owns gallery/reader state, `certificates-content.mjs` owns course facts and media addresses, `certifications.css` owns only this section/portal, and `certifications-motion.mjs` owns its optional entry assembly. Existing About scene order, movement paths and durations are unchanged. `about-layout.mjs` adds measured certificate height to its existing backdrop compensation; desktop and 390px backdrop bounds match the pre-insertion measurements.

The installed React Aria dialog supplies containment, dismissal, scrolling and return focus. Fit/Zoom, Previous/Next, Close and original-file controls are explicit; movement stops at the first/last item. At a boundary, focus moves to the still-enabled paging button instead of falling to the page body. Zoom/error state resets on document change. Loading is announced; a failed full image keeps an original-file link. Route exit removes the overlay and scroll lock.

New motion: 450ms line; 650ms documents with 110ms stagger; 400ms captions with 260ms plus stagger delay. Static content is always visible. Focus/reduced motion settle it; hidden-tab animation pauses, and observer failure leaves content intact. Cleanup disconnects observers/listeners and cancels running animations. Existing About/Home/Contact animation owners are not replaced.

Eight optimized WebPs (four previews/four full images) and four originals are under `frontend/public/media/certificates/`. Full images and originals load on demand. All twelve paths are classified `general` in the client-owned public-assets map, so booking OFF/unknown cannot hide education evidence. The shared booking package, data, settings, providers and permissions are unchanged.

## Focused proof and publication

13/13 dedicated certificate checks pass. Coverage is 100% statements (131/131), functions (36/36) and lines (63/63), and 98.07% branches (51/52); each included file exceeds 90% in every applicable measure. Coverage covers only this feature and its About layout owner. The checks cover content, fit/zoom/navigation, image failure, boundary focus, dismissal, unmount, optional animation, reduced motion/visibility, observation failure and backdrop measurement. Browser review covers 320×800, 390×844, 768×1024, 1440×900 and 1920×1080, including keyboard containment/return, outside/Escape close, document boundaries, image failure and route cleanup. No horizontal overflow or page errors were observed. The inspectable component preview is `frontend/tests/preview/certifications.html`; it is excluded from production output.

Use `npx vitest run --config vitest.certifications.config.mjs --coverage` from frontend. Production build and compiled output checks also enforce all certificate classifications and exclude private previews. No full local/hosted suite or real provider/customer transaction is part of this programme.

Publication uses the existing GitHub main → existing Vercel connection → official domain. Vercel remains disconnected from Codex. Actual publication status, source/asset hashes and read-only live observations are recorded in the client study's evidence and its README; a Git push alone is not publication proof. Recovery is a normal scoped revert without any customer-data change.
