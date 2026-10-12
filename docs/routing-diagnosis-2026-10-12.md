# Staff address and Reviews: confirmed causes and repairs

12 October 2026. These repairs are included with the authorized About certificate/Reviews publication. Booking stays ON. Company settings, authentication, customer records and the shared booking package are unchanged. Source changes and online proof are separate; actual release readbacks live in `design-review/2026-10-12-about-certifications/`.

## Older staff address

The existing shared handler in `appointment-system/engine/appointment_system/studio.py` supports `/studio/calendar` as an alias of `/studio`. Two host omissions caused the 404: the generated backend-path list exported only `/studio` and `/enquiries-studio`, and Vercel lacked the calendar alias rewrite. Both omissions were read from GitHub main, and the original failure was reproduced with valid synthetic signed ON state.

The bounded repair adds `/studio/calendar` to backend paths and exact `/studio/calendar` and `/studio/calendar/` rewrites to the existing `/api` handler. It adds no catch-all, new staff portal, authentication exception or shared-package divergence.

The local contract check passes four groups: all three staff URL forms reach the existing handler while ON; all deny while OFF; all deny for unknown state; exact host rewrites exist with no obsolete Reviews redirect. Synthetic signing state is test-only. No staff sign-in or calendar mutation is performed.

## Reviews visibility

The previous implementation was local and uncommitted. GitHub main and the published host still had the permanent `/testimonials` → `/about` redirect, independently observed as HTTP 308. Removing that exact redirect, exporting the public page and publishing the reviewed source addresses the cause.

The shared header/footer each gain one Reviews entry. Booking's existing sticky header uses that same component. The natural extra Home placement is an existing-style FAQ linking to the page. It now points to the complete page and explains that people can read feedback by service or open a full account. See [the Reviews record](testimonials-page.md).

The later one-section presentation had a separate deterministic cause: the public review collection was empty, so the existing component correctly hid its four content-dependent chapters. The owner now confirms all twelve accepted accounts were approved by Madhuri as legitimate and authorizes publication. Moving those exact accounts into the single public source restores the complete five-chapter design without changing its layout, styling or choreography. The current publication proof is in `design-review/2026-10-12-approved-reviews-publication/`.

## Booking cancellation: set aside

The owner asked to stop this investigation. No timeout, host guard, provider connection or booking workflow change is included.

The check was asking whether the host could read whether booking was ON or OFF before its 2,000ms deadline, so it could serve the appropriate guarded page/assets. Aborting that outgoing read during timeout cleanup can be expected. It was not a customer appointment cancellation.

Retained worker evidence for 12:39:55–12:41:10 UTC contains 157 state-read events: 156 HTTP 200/OK and one cancellation at 12:40:12.302 UTC after 1,966ms. That record alone does not prove the initiating cause, the browser asset involved, or that the 34ms difference from the host deadline is itself faulty. The corresponding originating Vercel request record was unavailable. It was evidence to correlate, not grounds for a guessed repair.

The connected Vercel account is unrelated. Saved local access returned 403 and the exact dashboard URL required login; no account connection/switch was made. No further log access is planned. Subsequent successful asset/page reads did not repair or disprove the original failed case. The dated [105/107 hosted report](hosted-checks-2026-10-12.md) remains unchanged.

The exact staff/Reviews changes can ship independently of this unproven historical issue. No cache bypass, permissive ON fallback, arbitrary timeout increase, customer submission or provider message is introduced.
