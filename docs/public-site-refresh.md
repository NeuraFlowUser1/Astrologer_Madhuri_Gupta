# Sarsa public website: source, checks and release

This guide describes the owner-approved 9 October 2026 public-site programme. It covers Home, About, Services, four service pages, Contact, three policy pages and the Booking page's common frame/local scrolling integration: twelve public routes in total. The programme has 40 acceptance groups covering the 28 feedback requests and the outdated booking-email wording.

## Current implementation

- All public routes share `SiteHeader`, `SiteFooter` and the first keyboard-accessible skip link. The phone menu closes on Escape, outside activation or navigation. Resizing transfers focus to an equivalent visible link when needed.
- Home fills the opening screen without stretching its image. The owner introduction, illustrated services, combined shield/process, eight exclusive questions and closing actions use the agreed English/Hindi copy.
- About has a smooth approach link, useful actions and four separate Explore/Book choices. The old `#consultations` link still reaches the starting-point section.
- Services has four illustrated entries, a service-choice guide, Jyotish terms and useful preparation text. Each service keeps its existing route and validated booking handoff. Kundli Prediction retains birth-chart, dasha and gochar explanations.
- Contact uses normal-flow panels, the original enquiry coordinator, the exact owner address `8, Gailana Road, LIC Colony, Agra - 282007`, the pin `https://maps.app.goo.gl/CwQftW8iYfxAZFDo8` and Google's own exported embed. The numbered questions sit outside the answer panels. No key or replacement Google client is required for this public map.
- A Contact topic is applied once only to a writable draft. A later topic action cannot overwrite a busy/verifying request or be replayed after restart. Scroll arrival focuses the current name/code/verification/result state; newer form error/result focus cancels pending page scrolling.
- The back-to-top control appears after 600px, hides below 400px and yields while a visitor edits the Contact form. It returns focus to the opening heading. It is not added over the Booking page's existing controls.
- Booking retains the same form, service IDs, phone/email rules, controller, payment, receipt, PDF, recovery and provider contracts. Its four-step scroll adapter receives the actual connected shared header, measures the header and strip, and uses a 16px phone/20px computer gap. The step strip stays below the measured header.

The shared booking-state owner alone decides availability. OFF/unknown hides booking entry points and does not start booking-only imports or policy calls; enquiries remain independent. A transient recheck retains the existing form without permitting a new operation. The client does not invent an ON state after a failed read.

## Design and lifecycle boundaries

The public palette uses paper `#f7f5ef`, forest `#26483d`, deep green `#183d31`, sage `#e8eddf` and brass `#9c7335`. Public typography uses licensed local Cinzel/Outfit with a Devanagari subset. Public titles are 36–56px on computers and 32–38px on phones, section titles around 29–40px, body text 17–18px and actions 15–16px. The common bar normally measures 80px/72px, but its actual measured height owns every offset when enlarged text wraps.

Public page styles are scoped to `.sarsa-public`; the existing Booking form keeps its own theme and controls. The old local frames, unused page-motion controllers and unused sample components are retired after import/source review. Original copies and retirement hashes remain outside the publishable checkout. No common-system file is retired or changed by this programme.

Service attention highlights at most two distinct cards once per mounted grid and ends within 2,040ms. Interaction, hidden state, reduced motion or cleanup ends it permanently for that mounted visit. Missing/failed optional observation leaves ordinary readable cards. There are no ambient movement loops or pause controls.

One router-owned anchor helper manages 260ms movement, bounded lazy targets, repeated hashes and history. Booking retains its separate 220ms step movement. Both cancel on wheel/touch/pointer, scroll keys, resize, hidden state, changed motion preference or unmount. Contact result/error focus takes precedence. No navigation or animation code stores drafts, restarts an email code or remounts the booking controller.

## Reproducible qualification

Run the production build first, then the commands below with Node 22 and the committed lockfile. Keep each report directory outside source and distinct from the other runs.

```sh
npm ci --prefix frontend
npm --prefix frontend run build
npm --prefix frontend run lint
npm --prefix frontend run check:public-site
SARSA_EVIDENCE_DIR=/tmp/sarsa-units npm --prefix frontend run test:public-site
SARSA_AXE_SOURCE=/path/to/axe-core/axe.min.js SARSA_EVIDENCE_DIR=/tmp/sarsa-browser npm --prefix frontend run test:public-site:browser
SARSA_BASELINE_ROOT=/path/to/built-original-project SARSA_EVIDENCE_DIR=/tmp/sarsa-performance npm --prefix frontend run test:public-site:performance
```

The accessibility tool is the separately installed testing-only `axe-core` 4.13.0; its script path is supplied explicitly. It is never loaded by the website or added to a customer bundle. Use the installed Playwright 1.63.0 browser binaries for Chromium, Firefox and WebKit. The checked programme uses Chromium's eight declared screen sizes, plus phone/computer checks in Firefox and WebKit. Screenshots and automated scans supplement actual visual and keyboard inspection; they do not establish physical-phone/native-screen-reader acceptance.

Unit coverage includes every active client JS/TS file, the build scripts, proxy and Vite configuration, with **no exclusions** and at least 90% statements, branches, functions and lines. The two pure re-export modules have no executable statements and remain in the audited inventory. Node build/proxy helpers run with actual instrumentation outside Vitest's VM because Tailwind uses native module hooks. Their original-source counters are merged, never averaged. Test-only JSON loading matches Vite's supported imports. Applicable existing booking, enquiry and callback-recovery checks remain included.

Browser checks use the actual built pages and unchanged contained routing with local synthetic responses. They cannot send an application request to the live websites or providers. OFF/unknown, service/date/code retention, Contact verification/error/result focus, native exclusive questions, menus, history, cancellation, enlarged text, reduced motion and blocked art/fonts are explicit scenarios. The Google embed itself requires a separate read-only public provider observation; a blocked-iframe fixture is not a claim that the real map was rendered.

The performance comparison uses original main `fef4f4e48eb87fe748c9d05b3be3ce4f27f6a548` with the same locked dependencies. Five cold samples per 390px/1440px primary viewport use Chromium, 4× CPU slowdown, 1.6Mbps download, 750Kbps upload, 150ms latency and the same 30ms synthetic response delay. Both local built-source transports gzip text, matching the observed official-host compression. External Google fonts/maps are blocked equally; new local fonts are included. Main-content paint has a 2.5-second median target, layout shift at most 0.1 and tested input-to-next-paint at most 200ms. Real menu/FAQ/Contact typing/booking-step events are recorded. These are bounded local lab observations, not field percentiles, provider latency or Google iframe speed.

New fonts must stay below 300KiB, each original vector below 20KiB, desktop/phone hero variants below 300/160KiB and the portrait below 180KiB. New total JavaScript may add at most 25KiB gzip against the same baseline. Only Home preloads its responsive hero; other generated routes remove those preloads. The main region reserves opening-screen space while a lazy route loads, preventing the footer from appearing early and moving away.

## Protected system and publication

The unchanged contained package digest is `97ab5d49fc559eb1acdeb7157d4561134d1bad824cca298506f48b2a9d32b49d`, with 573 manifest files and 36 migrations. Package verification and a separate Python import with outbound connections forbidden prove the deployment wrapper still starts. Without private configuration it returns the expected unavailable response; this is not a configured live-provider test.

Freeze a clean local candidate commit before the complete qualification. Record its SHA/tree, lock hashes, package digest and public-source/asset identities outside the candidate checkout. Source repairs produce a new candidate and invalidate dependent checks. Preserve failed/incomplete diagnostic reports with their original source identity.

Publish that same qualified commit to the existing main branch and observe the existing Vercel auto-deployment on `https://www.sarsajyotishsansthan.com`. Compare actual HTML/JS/CSS/media identities with the candidate, then check public routes and booking readiness read-only. Do not send a new enquiry, pay, alter prices or turn production booking OFF for this release. Ten minutes without an observed build triggers investigation of actual Git/deployment/domain evidence; repeated empty pushes are not a repair.

If rollback is needed, inspect current main and use a reviewed revert of this programme's commit, preserving unrelated later work. Verify that revert through the same official domain. There is no database/provider/key rollback because those contracts are unchanged. Prior real payment, Meet, email, spreadsheet and backup acceptance stays dated in [the booking operating guide](appointment-system-release.md); it is not relabelled as fresh public-site proof. Chronological staff-note history remains deferred.
