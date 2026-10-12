# Sarsa hosted verification — 12 October 2026

The owner requested documentation alignment and the entire hosted test suite on 12 October. The current checkout has local unit, compiled-browser and isolated booking-system tests, but no existing full hosted runner. Those commands must not be relabelled as live tests. The new repeatable read-only browser review is `frontend/tests/hosted/read-only-review.js`.

## Scope and boundaries

Run against the existing official domain, `https://www.sarsajyotishsansthan.com`, without publishing local changes. Check every route in the current live sitemap, the name-and-phone access page, shared navigation, metadata, internal destinations, images, desktop/phone layouts, original motion, FAQs, service-image controls, booking selection/date browsing, public configuration and unauthenticated private-page boundaries. Additional narrow-phone, tablet and wide-desktop checks cover the principal pages.

The browser uses fresh isolated contexts and actual hosted responses. Same-origin methods other than GET/HEAD are blocked before transmission. No mocked application response, customer credential, real customer lookup, booking creation, payment, enquiry, email, login, company-setting change, deployment, database write or background-job dispatch is part of this read-only review. Requests may produce ordinary access/rate-limit logs. Third-party map/font reads are observations, not provider acceptance. A controlled transactional journey was separately raised with the owner and has not been authorized with its required test details.

The pending Testimonials page cannot receive hosted acceptance while unpublished. Its current live redirect to About is an expected observation of the existing release, not a passing test of the new page. The accepted design and local proof remain in [the Testimonials record](testimonials-page.md). Invented accounts remain private.

## Execution and evidence

Status: the complete stated read-only assessment finished. **105 of 107 unique cases passed (98.1%); two cases failed. This is not a clean acceptance result.** No application code, hosting rule, booking setting, provider configuration, database record or live deployment was changed during this assessment.

| Area | Passed / executed | Practical scope |
| --- | --- | --- |
| Public page and layout checks | 37 / 38 | All twelve current sitemap pages plus the booking-access page at 390×844 and 1440×900; Home, Services, Contact and Booking also at 320×740, 768×1024 and 1920×1080. The stricter desktop Booking check failed once. |
| Interaction checks | 8 / 8 | Exclusive Home FAQs, back to top, combined Home stages and hover, About stages/hover/service actions, Contact fields/map, booking/date/draft controls, name-and-phone form/old entry, client navigation, and an additional booking-through-review check. Related assertions share cases; this is eight cases, not one case per listed control. |
| Service imagery and controls | 5 / 5 | Directory pictures/actions/divider plus three explanation choices and two manually selected pictures on each of four service pages. |
| HTTP, configuration and entry boundaries | 19 / 20 | Public service/health/policy reads, four availability reads, anonymous access rejection, sitemap/robots, unpublished Testimonials redirect, private sign-in entries and unknown-page handling. The older `/studio/calendar` address failed. |
| Internal links | 36 / 36 | Every distinct internal URL observed across the page/layout run, including anchors and all four service-specific booking links. |
| **Total** | **105 / 107** | Unique latest-case results; earlier attempts and subsequent observations remain separately recorded. |

The seven core phase runs contain 71 distinct cases. The 36-link audit is separate. Five Booking layout rows were rechecked after adding a wait for the actual live service choices; their latest results replace the earlier rows instead of adding five successes to the denominator. Subsequent successful file reads and visual captures do not replace the failed desktop Booking case. The pass percentage is 105 ÷ 107 × 100, rounded to one decimal.

The browser-tool runner accepts phases selected through the controlling blank tab's URL fragment: `routes-390`, `routes-1440`, `edges`, `interfaces`, `services`, `api`, `booking-layouts`. Use the Playwright browser tool with the runner's absolute filename. Each phase creates and closes its own contexts. The last phase strengthens Booking readiness at the five widths and reaches Review without submitting. Run the full set for the stated core assessment; one phase is not a complete hosted suite. The separate link-audit source records and exercises the actual observed URL set for this dated run.

Private evidence is in the client [hosted evidence directory](../../../design-review/2026-10-12-hosted-check/evidence/). `summary.json` owns the deduplicated case list, counts and failures. Per-phase JSON, the link audit, initial attempts and ten screenshots preserve the actual observations. This does not run the entire local suite or qualify real provider/customer operations.

## Two unresolved live observations

1. **Intermittent Booking file failure.** In the stricter Booking phase, 12:40:05–12:41:02 UTC, the 1440px Booking load failed. `/assets/browser-DjWqoSau.js` returned HTTP 404 and Chromium reported failure to import `/assets/Booking-CsOAh-fB.js`. The main heading never became visible within 30 seconds. Those files and the Booking HTML returned 200 on a subsequent read; later 1440px/390px captures loaded all four service choices. Those later observations are recovery evidence, not a repair or a clean rerun. The public entry asset remained `/assets/index-CQSNuqV4.js` in the observed reads; this does not independently establish a Git commit for the live deployment.

   Root cause is **unconfirmed**. The contained host guard can return 404 for booking assets when the ON-state projection is unavailable or not enabled; its read has a two-second timeout. That is a source-derived investigation lead, not proof of the cause of this request. Review actual host/worker logs for the observed window and retain the existing booking-OFF/unknown-state protections. Do not make those protections permissive to obtain a green check.

2. **Older staff calendar address.** `/studio/calendar` returned 404 on the test and subsequent probe. `/studio` and the other tested sign-in entries returned 200, and the three anonymous status reads returned 401. The backend still declares `/studio/calendar` as an alias for its existing staff HTML, but the generated `backend_paths` and Vercel rewrites omit that alias. The calendar lives inside `/studio`; no current `/studio` navigation link points to the older alias. This proves an address/export mismatch, not a failure of authenticated calendar operations, which were not exercised.

   Resolve whether the old alias remains a supported address, then align the existing host export and guard with that decision. Preserve the single staff portal and its current permissions; do not add another calendar implementation.

## Test review and evidence limits

The initial phone run measured the menu anchor's weight instead of its visible `.sarsa-nav-label`; the visible selected text was 700 and the anchor 500. That test assumption was corrected and the phone phase rerun. The initial interaction phase looked for hover movement while reduced motion was active and inspected `transform` even though the approved hover deliberately uses separate `translate`. It also assumed an exact date-button accessible name while React Aria combines its labels. The corrected phase waits for original assembly, enables normal motion for the hover check, inspects the independent hover property, targets the real popup button and proves its named dialog opens/closes. Both initial JSON reports remain; they are not product failures or passing acceptance.

The original Booking screenshots caught the pre-policy-loading state. The stricter readiness check uncovered the intermittent failure above. Two later `live-booking-*-loaded.jpg` images show all four decoded service pictures and supersede those initial images for visual review only. The failed test remains in the final denominator. Actual rendered review also covered the phone Services page and the Google Maps frame; the map displayed the supplied Gailana Road location.

Only Chromium was used. Home/combined and About stages were exercised with normal motion; layout/link cases used reduced motion. This is not full motion-equivalence, Safari, physical-device, sustained load, authenticated staff, real-customer lookup, payment, email-delivery, Google Meet, spreadsheet, backup or worker-recovery acceptance. A name-and-phone request was not sent. The booking-through-review case used a clearly synthetic local draft and stopped with acknowledgement unchecked and payment disabled; no customer details were transmitted.

## Next work

The [subsequent diagnosis](routing-diagnosis-2026-10-12.md) deterministically reproduced and repaired the staff host/export mismatch locally, and found one recorded state-request cancellation during the failed Booking window. The exact Booking cause still needs the matching host log. Neither repair nor Testimonials has been published, so the above live results remain unchanged. The pending Testimonials page still needs genuine client feedback; its legacy hosting redirect is now removed locally. See [its current record](testimonials-page.md).
