# Sarsa hosted release gate — 17 October 2026

**Final result: 153/153 unique cases passed (100%),0 failures,1,558 assertions, 9/9 phases.** The complete final run used real responses from the official website,17 October 2026,10:49:54–10:55:49UTC. This is the entire documented hosted read-only gate. The complete local suite and real customer/provider acceptance are separate.

Published runtime source: **`bd8ecfd42e6d72516e123ad6b9e316dc29004287`**, pushed to GitHub main and `work/home-about-logo-20261017`. Ten actual public JavaScript/CSS/logo/favicon files match the locally qualified build byte-for-byte. The Home/About titles, meaningful headings, service links, studies and new logo are visible on the official site. The subsequent closeout changes only the read-only runner and documentation; it does not change runtime files.

Frozen final runner SHA256:`6d08d0fa70f9f3d11364d6a0e1c36a8c2873f1c4514d5a878a2c2c6e8c2df890`.

| Phase | Passed | Assertions |
| --- | ---: | ---: |
| routes-390 | 15/15 | 221 |
| routes-1440 | 15/15 | 221 |
| edges | 18/18 | 267 |
| interfaces | 9/9 | 136 |
| services | 5/5 | 82 |
| api | 37/37 | 230 |
| booking-layouts | 6/6 | 89 |
| prashna | 5/5 | 73 |
| links | 43/43 | 239 |
| **Total** | **153/153** | **1,558** |

Counts use distinct case labels. Repeated/earlier attempts are excluded from the final denominator. The final gate includes 53 page/layout cases, 20 interface/service/booking cases, 37 configuration/access cases and 43 observed internal destinations.153 divided by 153 gives 100%.

## What was proved online

- All 15 public routes at 390 and1440px, plus320/768/1920px edge layouts, with one title, shared frame, loaded images, selected menu emphasis, metadata, canonical URLs and no sideways overflow.
- The approved128px transparent shared logo and64px favicon across the layout cases. Home/About identity,15+ experience, all five quick service destinations, source-backed studies, original 660/940px About surface, reduced-motion final state and exact browser titles.
- Mouse activation keeps focus on the activated Meet link and reaches the measured scroll position. Keyboard activation moves focus to the existing outside-scene destination. Original combined Home choreography, step hover, About approach and five Explore/Book service pairs remain.
- Services imagery and photo controls, Contact/Google Map/form presentation, nine Home FAQs and back-to-top behavior, booking-detail entry and old help redirect, optional booking email, native date picker, tab-return draft retention and booking through Review without submitting.
- Saved booking state remains ON with five enabled services. Original four fixed fees and one 30-minute Google Meet appointment remain. Prashna is ₹1,100 per question,1–10 questions; actual 1/3/10 server totals and native displays agree. Changes invalidate the old selected time and keep payment unavailable until ordinary requirements are met.
- Anonymous protected entries remain protected. The thirteen retired certificate public paths still return404. No certificate gallery/reader was restored.
- 43 distinct actually observed internal URLs return the expected destinations; hash targets exist.

A separate actual-hosted comparison matches the approved mockup at eight widths for both pages: **16/16 layouts, 424 compared elements, 0 measured geometry/style/content differences,0 horizontal overflow and 0 motion fallback/page errors**. Script-free Home/About reading content also returns HTTP200 with the same approved facts and no overflow. These are Chromium observations; they do not claim physical-device or Safari proof.

## Diagnosis and honest rerun history

The first six-phase attempt recorded 96/99 cases passing. Three check failures were investigated before changing anything:

1. Two new checks used a mouse click but expected the focus behavior reserved for keyboard activation. Source inspection and actual pointer/Enter traces proved the distinction. The final checks explicitly verify both pointer scroll/link focus and keyboard destination focus. No scrolling or motion implementation was changed.
2. A booking-details check inspected the initial unavailable boundary before actual booking-state admission finished. In a separate private diagnostic, the real unmodified GET response was delayed 1400ms: the early unavailable heading was visible at 2227ms and the real two-field form at 4515ms. The final gate waits for the actual form before strictly checking both required fields, no reference/code field and native empty-form rejection. It still fails if the form never arrives. No booking route, policy, shared package or timeout was changed. The diagnostic delay is **not** used in the complete final gate.

The entire nine-phase gate was rerun on the final frozen runner and published runtime. The earlier reports and runner remain in `initial-run/`; `interface-diagnosis.json` records actual observations. They are not relabelled as passing. All final phase reports are in `final-run/`, and `summary.json` owns the final unique case list/counts.

## Safety and limits

Fresh contexts block same-origin methods other than GET/HEAD before transmission. Explicit request-context calls use GET only. Final results contain **0 attempted/blocked unsafe requests,0 captured warnings and 0 captured third-party failures**. Synthetic names/phone numbers exist only in isolated local browser drafts; acknowledgement/payment is not submitted. No real booking, payment, customer lookup, enquiry, message, email, login, setting save, database edit, queue dispatch, authenticated staff action, Vercel reconnection or manually dispatched GitHub Action occurred.

This is not fresh Meet/payment/email/spreadsheet/backup/worker recovery acceptance, sustained-load, screen-reader, authenticated staff, Safari or physical-device proof. The historical Booking background-request cancellation diagnosis remains set aside; no repair is claimed. Existing large PDF/font build advisories remain.

## Evidence and rerun

Private client evidence: `design-review/2026-10-17-hero-brand-hosted-gate/` and `design-review/2026-10-17-hero-brand-implementation/`. The latter contains publication hashes, before/after source identities, focused 62/62/100%-of-ten-owner coverage, approved/current comparisons, intermediate/native traces, lower About bounds and opened screenshots. No credentials or real customer records appear in these reports.

The current source runner remains `frontend/tests/hosted/read-only-review.js`. Use the Playwright browser tool with its absolute filename. The controlling blank tab's fragment chooses `routes-390`, `routes-1440`, `edges`, `interfaces`, `services`, `api`, `booking-layouts`, `prashna`, and finally `links?` followed by the URI-encoded JSON array of distinct actual `internalLinks` collected from the other reports. All nine phases are required. The private batch wrapper uses separate fresh contexts and the same frozen runner. Future full reruns require owner authorization; ordinary focused checks remain part of approved changes.
