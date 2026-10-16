# Sarsa hosted release gate — 16 October 2026

**Final result: 151/151 unique cases passed (100%), zero failures, 1, 390 assertions.** All nine phases completed against the existing official domain with real hosted responses. This is the entire documented hosted read-only gate, not the entire local suite or real provider/customer acceptance.

Runtime source: `01e06fa1344021055db77d144a869890d803d5db`. Final runner SHA256: `3e243f6123da7ae97bb4fbc65b79ee9f351d013865926d1fd485c4d70256c01f`. Final run: 2026-10-16T22:12:22.922Z to 2026-10-16T22:17:29.018Z. The reviewed website files are unchanged by this testing/documentation closeout.

## Coverage and counts

| Area | Passed / executed | Scope |
| --- | --- | --- |
| Phone routes | 15/15 |All 14 sitemap pages plus name-and-phone booking access at 390×844 |
| Desktop routes | 15/15 |The same routes at 1440×900 |
| Edge layouts | 18/18 |Home, About, Services, Prashna, Contact and Booking at 320×740, 768×1024 and 1920×1080 |
| Existing interface controls | 7/7 |Nine exclusive Home FAQs/back to top, original Home/About stages/hover, Contact/map, booking/date/draft, booking-access form/legacy redirect, navigation |
| Existing service imagery | 5/5 |Five-card directory/actions/divider and the original four two-picture/three-topic stories |
| Configuration, access and retirement | 37/37 |Actual policy/health/state, five availability reads, 1/3/10 server quantities, 13 retired certificate 404s, sitemap/robots, 12 approved Reviews, private sign-in boundaries and unknown-page handling |
| Booking readiness and review | 6/6 |Fresh booking loads at five widths and Matching through Review without submitting |
| Prashna controls and motion | 5/5 |Phone/desktop 1/3/10 totals and fixed-service switch, topics/keyboard/FAQs, hero/ambient pause/reduced motion, Prashna through Review/count invalidation |
| Observed internal destinations | 43/43 |Distinct actually collected internal URLs, including real anchor existence |
| **Total** |**151/151**|Unique case labels; repeated full attempts are not added to the denominator |

For a shorter grouping: 53 page/layout cases, 18 interaction/booking cases, 37 configuration/access cases and 43 internal-link cases. These add to 151. Passing percentage is 151 ÷ 151 × 100.

The owner completed the protected Prashna service addition. The actual policy has exactly five enabled services. Original fixed fees remain ₹2,100 / ₹2,500 / ₹4,500 / ₹2,100. Prashna is ₹1,100 per question, 1–10 questions, no required preparation, one 30-minute Google Meet appointment. Actual server quotes and native displays agree on ₹1,100 / ₹3,300 / ₹11,000; slot durations stay 30 minutes. The new deep link selects Prashna. Switching to Matching restores ₹2,100 and removes quantity controls. Changing question count clears the selected time and keeps payment unavailable until the ordinary booking requirements are met.

The older staff calendar address returns the existing sign-in page. The prior intermittent Booking script failure was not reproduced in these runs. No host guard, timeout, worker or background-cancellation repair was made; its set-aside historical diagnosis is not claimed resolved.

## Safe execution and evidence

The owner explicitly requested the hosted gate after activation, superseding the initial implementation's no-tests instruction for this run. Fresh Chromium contexts use actual responses and block same-origin methods other than GET/HEAD before transmission. Explicit request-context calls use GET only. Final run recorded zero attempted/blocked unsafe requests, zero failed cases and zero captured warnings. Two through-Review drafts use a clearly synthetic local name/phone and stop before acknowledgement/payment; no customer details are transmitted.

No real booking, payment, lookup, enquiry, email, login, company-settings change, database edit, queue dispatch, Vercel reconnection or GitHub Actions dispatch was performed by Codex. The owner's earlier protected activation is distinct. Third-party map/font reads are normal page observations, not provider acceptance. No full local suite, coverage, physical-device, Safari, screen-reader, sustained-load, authenticated staff/calendar, fresh Meet/payment/email/spreadsheet/backup/worker recovery acceptance is claimed.

Private client evidence: `design-review/2026-10-16-prashna-hosted-gate/`, outside this application Git root. `summary.json` owns the final unique case list/counts. `third-run/` contains all final phase reports. Initial phase JSON and `final-run/` retain attempts 1 and 2 respectively; that older folder name does not identify the current result. Frozen runner versions and the image-load diagnosis remain. Public documentation contains no credentials, real customer records or private settings journal.

Manual visual review additionally captures the enabled card/date/count/fee at 1440, 390 and 320px and a 390px through-Review draft. Settled viewport captures explicitly supersede early element captures that caught loading or a sticky overlay. All final screenshots were opened individually. Actual 10-question totals are ₹11,000 at all three widths with 0px horizontal overflow; three-question Review is ₹3,300 with payment disabled and one 30-minute Google Meet appointment. Fresh anonymous company-settings/control reads return 401.

## Earlier attempts and deterministic corrections

1. First complete run: 150/151. An inherited test expected eight Home FAQs. The approved Reviews integration gives nine; source confirms the exact ninth question and destination. The runner now strictly requires nine plus the Reviews link. No FAQ was removed.
2. Second complete run: 149/151. Prediction/Numerology image checks inspected `complete` immediately after the picture counter changed. Fresh browser traces showed both intended images finishing 49/66ms later with HTTP 200 and naturalWidth 640. The component already decodes matching responsive images and retains the old picture during normal-motion fade. The runner now waits for the intended rendered source to complete, then retains the strict positive natural-width check. Broken images still fail. No product/media/motion code changed.
3. Third complete run: 151/151 on the corrected frozen runner. Earlier failures/results were not overwritten or relabelled as passing.

The current runner remains `frontend/tests/hosted/read-only-review.js`. Use the Playwright browser tool with its absolute filename. The controlling blank tab's fragment chooses one phase: `routes-390`, `routes-1440`, `edges`, `interfaces`, `services`, `api`, `booking-layouts`, `prashna`. The final `links` phase uses `about:blank#links?` followed by the URI-encoded JSON array of distinct actual `internalLinks` collected from those reports. Execute all nine phases for this gate; one phase is not the full run. Future complete reruns still require the owner's explicit permission. Focused checks remain within the repository's ordinary change workflow.
