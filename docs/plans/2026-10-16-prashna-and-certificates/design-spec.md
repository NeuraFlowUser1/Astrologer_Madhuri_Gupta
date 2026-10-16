> Accepted planning snapshot. Planning-stage observations below are historical. See [the current feature guide](../../prashna-kundali.md) for implementation, publication and saved-settings status. Private study files and screenshots remain outside this repository and hosting export.

# Design intent and implementation specifications

16 October 2026. Proposed values for the new/changed parts, grounded in the current rendered Sarsa site and source. Existing unrelated selectors, media and timelines remain the baseline. The approved interactive study is retained privately in the client design-review folder.

## A. Design rules and tokens

**Design intent:** Prashna should feel like the fifth member of the same service family. Readers should immediately understand what it is, what they can ask, what they need and what they pay. Certificate removal should feel like a clean editorial omission, with no empty chapter or replacement credential claims.

Use the current Georgia headings and system sans-serif body. Do not follow the inherited legacy Cinzel/Outfit description over the verified public site's current fonts. Do not introduce new external fonts, theme, dark-mode switch, ornamental frame system or animation library.

| Token / role | Concrete value for additions |
| --- | --- |
| Page paper | #f7f5ef |
| Light paper / image note | #fffdf8 |
| Warm chapter | #f2e9da |
| Sage chapter | #e9ece2; new card may use existing #f0f0e6 |
| Forest / primary action | #26483d; dark chapter #183d31 |
| Main ink | #21392f |
| Secondary text | #526456; do not use pale sage for essential copy |
| Decorative sage / bronze | #7c8e68 / #a6814d; not small-text colors |
| Border | #bec9b4, 1px; only one visible enclosing border |
| Card radius / image radius | Existing Home 24px / 20px; directory 26px / 20px; new detail panels 24px |
| Resting depth where a panel is raised | 0 14px 30px #26483d15 |
| New-card hover depth | 0 20px 38px #26483d22; translateY(-4px) only on fine hover pointers |
| New-action focus | 3px solid #26483d, outline-offset 3px on light surfaces; #fffdf8 on forest |
| New-action transition | Reuse --ease-action; current timing 220ms. Transform, background and shadow explicitly named. Press 120ms, translateY(1px). No transition: all. |
| New explanatory motion curve | Existing smoothstep phase: t²(3−2t); same phase model as Sarsa scenes. Do not replace old easing curves. |
| New ambient cycle only | cubic-bezier(.77,0,.175,1), 0/50/100% keyframes; do not change existing ambient/action tokens |
| Media / artwork / copy / focus layers | 0 / 1 / 2 / 3 within an isolated section; review toolbar belongs outside the product composition |

Typography for new content:

| Role | Desktop | Phone ≤650px |
| --- | --- | --- |
| Prashna h1 | clamp(44px,4vw,56px), 1.08 line-height, Georgia 400, −.025em | 36px, 1.12 |
| Section h2 | 36–40px, 1.18, Georgia 400 | 30px, 1.2 |
| Home service h3 | 28px, 1.18 | 28px, 1.2 |
| Directory service h2 | 34px, 1.15 | 30px, 1.2 |
| About service title | Preserve current 25px serif | 22px; allow wrapping, never collide with actions |
| Intro copy | 18px, 1.65, max 58ch | 16px, 1.65 |
| Body / example text | 17px, 1.65, max 62ch | 16px, 1.65 |
| Labels / facts | 15px, 1.5; weights 600/700 when meaningful | 15px, 1.5 |
| Buttons | 15–16px, 1.4, weight 700, minimum 48px tall | 16px, minimum 48px tall |
| Eyebrow | 12–13px, 1.5, weight 700, .1em tracking | 12px; no essential explanation only here |
| Fee / calculated total | 30–36px, 1.15, Georgia; tabular numerals | 30px |

Preserve old type outside this scope. Explicit unit/quantity labels and selected states do the work; bold only key facts, not whole paragraphs. Hindi is short and in everyday Roman letters: “Apna sawaal saath laayein.” No mystical outcome promise or cryptic headline.

Responsive rules: Home retains 6% horizontal gutters; at ≥1600px preserve the existing1240px usable-width cap with gutters max(6%,(100%−1240px)/2). Its current phone gutter remains22px. Directory/detail outer maximum 1200px including 48px desktop gutters; phone gutters 24px, 20px at ≤350px. New detail content width is therefore 1104px at a 1440px viewport. Use minmax(0,1fr), min-width:0 and naturally wrapping text. No fixed viewport-height chapter or fixed content height on phones. Large split layouts change at 900px; ordinary existing card grids change at 650px.

## B. Home — fifth service card

**Design intent:** Add Prashna visibly without changing the already accepted four cards. A fifth half-card would look accidental; use a complete row.

**Implementation spec:**

- Keep Matching, Prediction, Vastu and Numerology in the current 2×2 desktop order, with existing image, copy, icon, Explore action, 22px gap and attention behavior.
- Append a Prashna article with class service service--prashna, not a global last-child rule.
- At ≥900px: span both columns; display image and copy as 41% / remaining width with 36px gap, 30px vertical / 34px horizontal padding. Image height 240px, radius 20px. Natural height is max(240px image height, actual copy height) +60px vertical padding +2px border; never impose a max-height or clip copy. Align its copy group centrally within that image height.
- At 651–899px: still span both columns, but stack image above copy; 26px padding, 24px image-to-copy gap. Image aspect-ratio2:1, height:auto, width100%. This avoids the narrow, tall crop of a 35% image column. Grow naturally with copy.
- At ≤650px: normal one-column card; padding 25px 26px, image 190px tall, 24px gap before copy. All content in document order; same radius/depth as current cards.
- Title “Prashna Kundali”. Copy: “Have a specific question about work, family or a decision? Explore it through Prashna Kundali. You can book without your birth details.”
- Fact line: “One question or several, in one appointment.” No fee duplication on Home: the directory/detail/booking show the approved exact fee.
- Index 05; small persistent paper/chart motif in the same 53×53px Home icon area. No floating question-mark badge or unconnected decorative endpoint.
- Explore action points to /services/prashna-kundali. Do not add an extra direct Book CTA only to this Home card; preserve the existing Home card pattern.
- Existing randomized visible-card attention applies to all five. Hover/focus takes precedence, uses original glow/lift and returns cleanly. Existing four motion must not restart just because the fifth exists.
- The new row adds normal-flow height before the combined chapter. Keep the chapter's original 5000ms sequence, paths and relative positions; do not compress or merge it again.

FAQ deltas only:

1. “Which service should I choose?” — retain the current four explanations, then add: “For a specific question without a birth-chart reading, explore Prashna Kundali.” Link the service name.
2. Unknown birth time — retain the existing advice for birth-chart services, then add: “Prashna Kundali can be booked without birth details.” Link naturally. Do not imply all other services have become birth-detail-free.

## C. About — remove certificates and add one service row

**Design intent:** Let Madhuri's personal introduction lead directly into the existing service choices. Remove the requested education showcase, not the About page's personality.

**Implementation spec:**

- Remove the certificate section/import/viewer without inserting a replacement credential paragraph or empty anchor.
- Preserve the personal portrait and MarginArt; the next existing service-choice chapter uses its current sage background and 85px vertical padding (55px phone).
- Remove certificate-specific gap/padding/height measurement. No spacer equal to the removed measured 1588.515625px desktop gallery.
- Preserve current consultation grid 1fr / 1.1fr and 85px gap at large widths, current smaller-width gap and single column on phones.
- Service order: Prediction, Matching, Vastu, Numerology, Prashna. Original four rows keep their existing titles, links and numeral/arrow motion. Fifth row has Explore and Book, with accessible labels naming Prashna.
- At ≥1200px, keep current absolute action alignment only while the actual title/action footprints fit. For the new “Prashna Kundali” title this fits the current large row. At <1200px preserve the existing actions-beneath-title rule; mobile rows grow naturally.
- Row actions: ≥44px current minimum, 12px gap; title/number/action areas cannot overlap. Use existing buttons and current focus/active rules.
- Existing personal paragraph changes only its service enumeration: “The practice offers Kundli Prediction, Kundli Matching, Numerology, Vastu Consultation and Prashna Kundali.”

**Backdrop compensation, exact measurement rule:** Current root-relative welcome/invitation art compensates for added actions/certificate height. Keep the helper and its lifecycle. Add data-service-id={id} to each existing row and identify the original four IDs from that attribute, then calculate their identity-only height using the existing action subtraction. Let B = max(sum of those four identity heights, natural intro height); L = actual five-row list height. New growth G = max(0,L−B), with no certificate term. Set --about-row-growth = G px, --about-row-growth-60 = .6G px, --about-row-growth-56 = .56G px. Continue observing the root/list/intro, resize and font readiness; remove only the certificate observer.

Why freeze four identity rows: if the helper instead includes the new fifth identity row in its baseline, it cancels that new height out and the background art drifts. Natural intro dominance must still be respected, so simply adding one guessed row-height constant is also wrong. Measure real wrapped/action layouts, including Book hidden while OFF.

Fifth-row timing stays within the original 2925ms scene: start at .35+4×.08 = .67 (1959.75ms); end .65+4×.08 = .97 (2837.25ms). Preserve original four starts/ends. Keep 7150ms hero, 2437.5ms welcome and 2925ms other original scenes. No new scene counter or root-wide replay.

## D. Services directory and guide

**Design intent:** Make the new service easy to compare with the others and make per-question pricing clear before a visitor opens Booking.

**Implementation spec:**

- Keep existing 2×2 cards, 24px current grid gap, their media/motifs and right-aligned actions.
- Append a fifth card with class directory-card--prashna spanning both columns. At ≥900px: two internal columns, 41% image / remaining copy, 36px gap, existing directory card padding 38px (28px where current ≤1000px rule applies). Image 240px tall, 20px radius.
- At 651–899px: span both columns, normal image-above-copy order; image width100%, aspect-ratio2:1 and height:auto. Do not squeeze two CTAs into narrow side-by-side copy or stretch the photograph into a fixed220px-high slot.
- At ≤650px: normal one-column directory card, existing 24px padding and 190px photo, with both 48px actions full width as currently.
- Title “Prashna Kundali”. Description: “Have a specific question about work, family or a decision? Discuss it with Madhuri through a question-time chart. Birth details are not required to book.”
- When booking is displayed ON: “₹1,100 per question · 30 minutes · Google Meet”. Beneath it, “Choose 1–10 questions for one appointment.” No ambiguous “₹1,100” standing alone.
- Explore / Book use the existing visible sage/forest treatments, right alignment, 12px gap and 700-weight labels. Explore route is the new detail page; Book carries only service=prashna-kundali.
- Use the current directory card scene: 2100ms photo/motif/copy/action stages, unchanged even for the wide card. Preserve the established image-clip timing and don't substitute a generic small fade.
- Existing first-guide division remains 48px below the card grid, 32px phone. Append a fifth guide choice spanning both columns ≥651px, with 28px top breathing room where necessary; no single orphan column.
- New guide question: “A specific question on your mind?” Action: “Explore Prashna Kundali.” Keep the meaningful guide motif and current 2400ms guide scene; the fifth item delay .28 still fits.
- Add one natural explanatory sentence to the Jyotish guide: “Prashna Kundali starts with the time a specific question is asked.” Do not replace the four existing terms or their art.

## E. New Prashna page — six sections

Use explicit PrashnaKundali.jsx, rather than the generic detail page's numerology fallback. Root class .sarsa-prashna is full width; each chapter has one .prashna-wrap inner content grid (max1104px, width calc(100%−96px), phone calc(100%−48px), ≤350px calc(100%−40px)). Do not inherit a directory max-width on the whole page, which would contain the chapter backgrounds. Use data-prashna-scene values hero/difference/examples/preparation/fee/questions, and scope all new motion/art queries to this root. Reuse shared frame, navigation, booking guards, scroller and mountScenes. The finished page has no separate enquiry form, uploads, fake case study or invented review.

| Section | Design intent | Layout and content specifications |
| --- | --- | --- |
| 1. Prashna Kundali | State what the service is and lead to the right appointment | Warm #f2e9da; split 1fr/1fr, 64px gap, padding 72px 0 80px desktop / 40px 0 48px phone. At ≥900px a natural 580–680px chapter including content; never force height. Vector-art stage 500×375px maximum, 4:3 ratio, 24px radius; phone width100%, maximum height280px. H1 44–56px; plain copy and two natural CTAs. |
| 2. How Prashna Kundali is different | Explain question-time versus birth-chart reading in ordinary words | Paper #f7f5ef; 80px vertical desktop / 56px phone. Supporting still life on left, 44% width, 3:2 ratio, radius24px; comparison copy on right, 40px gap. Two simple labeled entries, no nested photo container. At <900px stack. |
| 3. Questions you can bring | Help a person recognize an appropriate kind of question | Sage #e9ece2; 80/56px padding. Three native tab buttons, 12px gap; two example entries in 1fr/1fr below, 24px gap. On phone the tab row wraps; examples stack. Tab labels 15–16px/700, selected forest fill + white text; unselected paper + ink. Do not make hover the only way to read examples. |
| 4. Before your appointment | Give three useful things to do without a second form | Paper; 72/56px padding. Three columns at ≥900px, stacked below; 24px gap. Number circles44px, headings24px desktop/22px phone, body16–17px. A connector is allowed only if it visibly joins the three real steps and remains in the settled design. No random draw-and-vanish ornament. |
| 5. Fee and appointment | Make quantity, total and time unambiguous | Forest #183d31; text #fffdf8, supporting #dce3d6; 72/56px padding. Lead “₹1,100 per question”. Three amount examples (1,3,10) in equal columns, all generated from catalogue fee; mobile one row per example. State one 30-minute Google Meet appointment and maximum 10 questions. One Book CTA; no separate calculator/checkout owner on this page. |
| 6. Questions before you book | Answer practical uncertainties and offer Contact without pressure | Warm paper; 72/56px padding. Five FAQs, single-open disclosure behavior matching Home, 18px/700 question, 16–17px answer. Final Book + Contact actions after a 32px gap, aligned to the same text grid; phone stack. Shared footer follows unchanged. |

### Exact draft customer copy

Hero:

- Eyebrow: “A specific question”
- H1: “Prashna Kundali”
- Supporting heading: “Discuss a specific question with Madhuri.”
- Body: “Prashna Kundali uses a chart based on the time a question is asked. Madhuri looks at the chart and discusses that question with you. You can book without your birth details.”
- Short Hindi: “Apna sawaal saath laayein.”
- Fee line: “₹1,100 per question · One 30-minute Google Meet appointment”
- Primary: “Book Prashna Kundali”; secondary: “See what you can ask” → examples anchor with the existing smooth scroller.

Difference section:

- “Prashna Kundali: starts with a specific question and the time it is asked. You do not need birth details to book.”
- “Kundli Prediction: explores your birth chart and a wider phase of life, using your birth details.” Natural link to the existing Prediction page.
- “If you are unsure which one fits your question, contact the practice before booking.”

Example categories and questions:

| Category | Two examples |
| --- | --- |
| Work and business | “Should I consider this new work opportunity?” / “What should I discuss before taking this business decision?” |
| Family and relationships | “What should I consider about this relationship decision?” / “How can I look at the family question that is worrying me?” |
| A decision ahead | “I am choosing between two options. How can I discuss this through Prashna?” / “What should I keep in mind about the next step I am considering?” |

They are examples of questions someone can bring, not promised answers, clinical advice or client success stories. Avoid “instant”, “guaranteed”, “100% accurate” or predictions about medical/legal/financial outcomes.

Preparation steps:

1. “Write down your question.” “A few clear words about what you want to discuss are enough. You may use the optional booking notes.”
2. “Choose how many questions.” “Select 1–10 questions while booking. You will see the full fee before payment.”
3. “Join your appointment.” “Keep your questions ready for the Google Meet conversation. Your confirmed booking shows the meeting details when ready.”

Fees:

“The fee depends on the number of questions you choose. The appointment is still one 30-minute conversation. Choose your question count in Booking, then check the total before payment.”

FAQs:

1. “Do I need my birth date or birth time?” → “They are not required to book Prashna Kundali. Bring the specific question you want to discuss.”
2. “Can I ask more than one question?” → “Yes. Choose between 1 and 10 questions while booking. The fee is ₹1,100 for each question.”
3. “Does a higher question count give me more time?” → “No. Each booking is one 30-minute appointment, including the questions you select.”
4. “Do I need to send my question separately?” → “No separate form is needed. You can use the optional notes while booking, or bring your question to the appointment.”
5. “What if I am unsure which service to book?” → “Read about Kundli Prediction, or contact the practice with your question before booking.” Both are real links.

On booking OFF: put the hero fee line and Section 5 purchase facts/examples inside BookingOnly; show a short Contact invitation in their place. Use BookingCopy for the preparation count step and fee/count FAQ answers, replacing them with ordinary Contact guidance. Hide all Book controls through the existing bindings. Retain the service explanation/examples and Contact actions. Do not expose hidden booking details by treating the new route as an unrestricted checkout. The new page itself remains general/public.

## F. New artwork and generated-image briefs

**Design intent:** Real material texture like the accepted service images, with a distinct question-time subject. No practitioner, client, office or fake certificate photograph. Existing eight service compositions remain.

Two new compositions, not a bank of unused images:

1. **prashna-kundali-primary** — 1536×1024 landscape master. Handmade cream paper with one North Indian chart, a small simple brass clock and a folded blank question note, forest-green cloth edge, soft natural light from upper left, calm material texture, editorial still life. Entire chart/clock/note inside x15–85%, y20–80%; no important content at the outer crop edges. No legible generated prose/numerals that could be mistaken for an actual chart, no person, room, garbled labels, watermark, gilded frame, religious figure or excessive flowers. Do not regenerate an existing Prediction still life with only a clock pasted on.
2. **prashna-kundali-supporting** — same size, family lighting/materials; closer arrangement of a closed question note, writing tool, clock and a partial chart sheet, open negative space upper right. Distinct camera angle/object arrangement. Keep all important objects x15–85%, y20–80%. No birth certificate, person, office, promises or fake testimonials.

Use the built-in image generation tool during implementation, inspect the actual results and revise if crop/objects fail. Keep prompts/source masters/provenance in client-only assets. The planning study's SVG is composition/motion evidence, not a claim that these two photos are generated or approved.

Renditions: primary 480/800/960/1200px wide; supporting 800/1200px wide, all 3:2 WebP. Reserve 1536×1024 intrinsic dimensions and stable wrapper size. object-fit:cover; starting object-position 50% 50%, adjusted only after inspecting actual cuts. Primary alt: “A question note, chart and brass clock on handmade paper.” Supporting alt: “A folded question note and writing tools beside a clock.” Rewrite alt if the generated result differs.

Budget: primary480 ≤60KB, primary800 ≤120KB, primary960 ≤150KB, primary1200 ≤220KB; supporting800 ≤120KB and1200 ≤220KB. Combined chosen 960px five-service images target ≤700,000 bytes; do not silently compress or replace old images to meet a guessed budget. If the new photo is too heavy, adjust its own encoding/composition/rendition selection. Existing maximum image207,416bytes and four-service set511,604bytes are historical inspection facts, not a performance test.

Use the primary photograph for Home/Services/Booking cards as the service identity image. The detail hero uses the permanent SVG assembly, rather than placing a second chart/clock/note over the same objects in a photograph. Use the supporting photograph once in the difference section. This keeps two purpose-made photographs and a distinct moving hero, without doubled objects or a photo nested inside another artwork frame. No image carousel is needed for two photos already shown, and no interactive hotspots are added without information they reveal.

Inline SVG instances must use React useId-derived gradient/filter IDs, so a thumbnail and hero cannot resolve another instance's definitions. Movement queries data-art-part inside the component root only.

Vector motif: 320×240 viewBox; one paper sheet, one simple four-house chart geometry, a question-note shape and small clock face. Strokes1.4–1.8px with consistent forest/sage/bronze, paper fills and one material shadow. It is decorative with aria-hidden=true; visible prose explains the concept. For 53px/80px motif uses, render a simplified paper/chart/clock variant; do not cram six labels into a thumbnail.

## G. Motion — deliberate multi-stage assembly

Existing timelines are protected. New Prashna motion tells the question/chart story through separate pieces; it must not be reduced to every object moving up 8px simultaneously.

Hero: **3600ms**, one shot on page entry using the existing scene owner. Content/CTAs remain usable; keyboard focus settles the section immediately. Time windows overlap intentionally:

| Window | Part / transition | Exact starting → final state |
| --- | --- | --- |
| 0–700ms | Foundation / art surface | opacity .25→1, scale .96→1. No surface stretch or layout change. |
| 450–1600ms | Two paper leaves open | Left/right leaf rotate −28°/+28° →0°, translateX +24px/−24px →0, scale .88→1 to keep their corners inside the stage. SVG transform-box:fill-box; origin at inner paper edge. Phone rotations −16°/+16°, 14px travel. |
| 1100–2300ms | Chart settles onto the opened paper | translateY28px→0, rotate−14°→0, opacity0→1. Phone18px/−8°. Persistent chart geometry; no temporary drawing strokes/dots. |
| 1750–2700ms | Question note moves into place | translate(−36px,20px)→(0,0), rotate−8°→0, opacity0→1. Phone(−20px,12px),−5°. Final note offset is defined in SVG, not a runtime measured drift. |
| 2300–3100ms | Clock docks beside note | translate(38px,−12px)→(0,0), rotate12°→0, opacity0→1. Phone(22px,−8px),8°. Never cover the heading or price. |
| 3100–3600ms | Settled hold | All parts at their final positions. No sudden reset or disappearing ornament. |

Foundation final canvas320×240 scales proportionally. Art's safe final positions: paper x56–238/y26–220; chart x93–203/y65–175; note x40–135/y153–211; clock center246,74 radius30. Note and clock remain entirely inside the viewBox even during the bounded movements; apply local art clipping only if an intermediate exceeds the planned safety margin, never crop meaningful final objects.

Ambient after assembly: note translatesY0→−4px→0 over8000ms; clock group rotates0→3°→0 over12000ms about its center. No moving clock hands/countdown or implication of an appointment's real time. Separate inner wrappers own ambient transforms so they cannot overwrite entrance transforms. Pause offscreen, hidden tab and focus/hover; reduced-motion preference shows the stable final art. No movement-control UI.

Other new section scenes:

| Section | Sequence | Duration |
| --- | --- | --- |
| Difference | Supporting image frame opens0–900ms; comparison leaves separate400–1500ms, translateX±28px→0 and rotate±3°→0; labels settle1200–2200ms; hold to2800ms | 2800ms |
| Examples | Three category controls establish0–700ms with70ms stagger; selected category's two example sheets separate500–1500ms from translateX±20px, rotate±2°; text settles1000–2000ms; hold | 2400ms |
| Preparation | Number markers arrive0–850ms with70ms stagger; step bodies unfold400–1500ms from scaleY.96→1/translateY14px→0; a meaningful permanent connector may settle1000–1800ms; hold | 2400ms |
| Fee | Fee label/amount settle0–650ms; three amount examples arrive350–1150ms with70ms stagger, translateY12px→0; appointment fact settles900–1450ms; hold | 1800ms |
| FAQ / closing | No theatrical delay on reading or disclosure. Initial chapter opacity/translateY12px settles0–600ms; user disclosures remain immediate/interruptible | 600ms |

Tab change: selected color/border updates immediately. Category activation settles the examples entrance locally before replacing its panel; do not restart the scene or retain hidden transforms from the old panel. A local interaction flag in the new renderer is sufficient; no shared scene API change is needed. Pointer-driven example content crossfade ≤180ms; retarget/cancel prior transition, preserve container readable height, no outgoing and incoming text stacked together. Keyboard changes are instant. Arrow keys/Home/End move the selected tab; Tab continues into its panel/links. On narrow screens the tab row wraps instead of horizontal-only hidden content.

Hover: raise actionable cards/steps4px and strengthen existing depth; number emphasis uses weight700 and a restrained bronze shadow. Touch gets no sticky hover. Focus rings are independent of shadows. Do not animate text scale/letter spacing, regenerate layouts, or install smooth-scroll interception.

Lifecycle: default HTML/CSS has readable final content. After refs mount, register scoped scenes; errors settle to visible rather than keeping opacity0. Unmount cancels frames/timers/observers/listeners and settles. Resize repaints current progress without replay. Reduced-motion changes settle immediately; final images/copy remain. The ambient observer has no ownership over form state, routing, booking availability or existing scenes.

## H. Booking presentation

**Design intent:** A visitor can see what they selected and what it costs, without interpreting an unlabeled amount.

- Keep the existing four radio cards and the service/date/details/review structure. Append a fifth radio label with class service-card service-card--prashna.
- At ≥651px the fifth card spans two columns, with an internal180px-wide image area and remaining label/facts, 24px gap and existing24px padding. The photo is180×120px (3:2). At ≤650px stack image above copy, with width100%, aspect-ratio3:2 and height:auto. Keep the old four thumbnails unchanged; the new Prashna thumbnail must not inherit their shallow88px crop.
- The service card reads “Prashna Kundali”, “₹1,100 per question · 30 minutes” and “Choose 1–10 questions”. Actual live policy supplies values.
- Native question select next to the date controls: label “Number of questions”, 48px minimum high, options1–10, selected1; hint “₹1,100 per question. One 30-minute appointment.” No question input for fixed services.
- Review adds “Questions: 3 × ₹1,100” and “Total consultation fee: ₹3,300” for the selected example. At ≤430px put the total label above the amount rather than forcing a three-line label beside it; use two deliberate lines for the payment button (action, then amount + arrow), ≥68px high. The amount/arrow stay together even at ₹11,000. Quantity edit returns to the appointment/count section through the existing measured scroller.
- Selected card: preserve the existing selected treatment and checked native radio. New per-question facts use15px/600, ordinary secondary facts15px. Do not depend on glow alone to show selection.
- Keep existing loading/error/recovery/freshness guards. The private study only demonstrates count/total styling; it has no backend, date availability, payment or contact submission.

## I. Responsive and state acceptance matrix

Primary screens: 1440×900 and390×844. Targeted narrow/wide cases: 1920×1080, 768×1024, 360×800 and320×740.

Check the specific changed objects: all fifth-card image safe zones, same-family framing, copy/actions wrapping, two-button alignment, selected radio, count label/options, fee unit and total, About numeral/action fit, comparison leaves' final positions, no sideways scroll, no generated prose/watermark, no duplicate border, no lonely half-width card.

Keyboard focus must be visible, settle in-flight sections and reach all actions. Tabs/FAQs must announce labels/current state. Failed imagery shows the existing service-art fallback with stable dimensions, not a blank paid-service card. Loading/failure cannot select a different service silently. Booking OFF hides purchase content through existing guards while keeping the new public explanation/Contact route usable.

The study contains layout/motion controls outside the customer-like composition. They are not a proposal for controls on the real site. Final photo crop, integrated native scenes and hosted saved settings still require implementation-time review; this plan does not claim pixel-perfect production proof before that work exists.
