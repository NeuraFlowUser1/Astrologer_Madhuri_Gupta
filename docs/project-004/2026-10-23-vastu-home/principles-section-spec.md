# Lower-page Vastu principles — approved private-draft refinement

23 October 2026. The owner asked for more depth and authentic terminology in the lower half, with illustrations and transitions. The upper introduction and picture story are accepted as the direction and must remain unchanged. This instruction authorises refining the private draft; it does not authorise website publication.

## Objective and source boundary

Add one compact illustrated chapter between the existing conversation prompts and preparation. Preserve all five existing chapters, the current hero image, upper copy, topic/photo interaction, colours, type, booking links and their current behaviour. The result has six chapters, with the new depth concentrated in one place.

Use authentic ideas with short plain-language explanations. Do not fabricate practitioner credentials, assessment techniques, reports, results or claims of scientific proof. The drawing is a traditional-framework illustration, not a diagnosis or an approved floor plan.

Research checked on 23 October:

- [IGNCA course outline](https://ignca.gov.in/hi/divisionss/academic-unit/short-term-certification-course/vastu-shastra/): Pancha-mahabhuta and the 64/81-pada mandalas are explicitly within traditional Vastu study.
- [81Matrix's architectural glossary](https://www.81matrix.com/resources/?lang=HI): mandala, pada as an individual cell, Brahmasthana as the central cells and the five-element terminology, with its named textual references.
- [A practising consultant's framework](https://mahanvedicvastu.com/vastu-consultation/): contemporary use of Brahmasthan and the five elements as parts of a whole-layout reading. Its services and asserted results are not Sarsa facts.

## Customer-facing content

Section title: **The principles behind the plan.**

Lead: **The layout, its centre and the qualities of each space are considered together.**

Three manually chosen views:

1. **Mandala → Vastu Purusha Mandala.** A traditional planning grid relates directions to different parts of a site. Its individual squares are called padas; 64- and 81-pada arrangements are among the classical forms. The grid gives the rooms a wider context.
2. **Brahmasthan → The central zone.** Brahmasthan names the centre of the mandala. What occupies that centre, how rooms connect around it, and where stairs or large fixed features sit are considered in relation to the whole layout.
3. **Five elements → Pancha Mahabhuta.** Earth, water, fire, air and space are known as Prithvi, Jala, Agni, Vayu and Akasha. This traditional framework gives a vocabulary for considering the qualities and uses of a space, alongside its direction and arrangement.

The exact words may be tightened during rendered review without adding a new service promise. The full Sanskrit/English labels appear in the selected explanation; concise controls remain readable on a phone. All three explanations must be available with keyboard, touch and assistive reading. No automatic switching or timed reading.

## Design Intent

Give the lower page a memorable, useful illustration that shows how a Vastu reading moves from the complete plan, to its centre, to qualities of space. A real framework and specific vocabulary provide depth. Keep the composition calm and compact, with one diagram changing states instead of a new series of text cards.

## Implementation Spec

- One forest panel using the current `#26483D`, ivory `#FFFDF8`, muted light sage `#DDE4D4` and restrained gold `#C8AC6C`. Border radius **26–28px**, desktop padding **40–44px**, phone padding **20–24px**; margin **24–40px** before/after. No global CSS change.
- Section heading **36–42px desktop**, **28–32px phone**; selected concept heading **28–32px desktop**, **25–28px phone**; body **16–17px**, line height **1.55–1.65**; control labels **14px**, minimum **44–46px** hit height. Reserve the maximum heading/body height across modes so controls and following content stay still.
- Desktop diagram/copy columns approximately **1.1fr / 1fr**, gap **32–40px**. At **800px** and below, use one column. Do not alter the existing upper 650/700/850px layout decisions.
- Native SVG viewBox **520 × 470**. Ivory paper plane, a **9 × 9 / 81-cell** illustrative grid, a restrained room outline and cardinal labels. Diagram is illustrative, not a universal room-direction prescription.
- Mandala mode: whole grid and plan visible. Brahmasthan mode: highlight the **central 3 × 3 cells of this particular 9 × 9 example**, soften surrounding lines. Five-element mode: replace the grid emphasis with five coherent symbols and readable Earth/Water/Fire/Air/Space labels. Hide cardinal labels in that mode so the diagram does not suggest element-to-direction assignments.
- Use code-native artwork for exact geometry and meaningful state changes; preserve the existing raster hero and story images. There is no reason to regenerate those accepted images.
- Entry uses one **2600ms** definition in the existing copied `mountScenes` owner: paper **0–700ms**, grid **350–1500ms**, plan **900–2200ms**, selected emphasis/copy **1500–2600ms**. Use the existing smoothstep phase function. Maximum entrance travel **14px**; scale **0.98 → 1**. Do not move reading text for style.
- Mode changes use **220–320ms** opacity/colour transitions with the existing action curve `cubic-bezier(.2,.7,.2,1)`. Keep state immediately consistent under repeated clicks. Use separate parent entrance and child mode layers so no element has two transform/opacity owners.
- Reduced motion shows the settled diagram and immediate mode changes. The existing engine's keyboard-to-settle, hidden-tab suspension, fallback and disposal remain. No added ambient loop or autoplay.
- Selected controls use ivory/forest contrast; unselected controls retain a visible light border; focus ring **3px** gold with **3–4px** offset. Every mode changes both the readable explanation and the labelled illustration.

## Ownership and preservation

- New private files: `preview/principles.css` and `preview/principles.mjs`, scoped only to the new chapter. Main preview gains the section, a stylesheet link, scene registration and lifecycle disposal. Existing `preview.css`, both upper section HTML blocks, hero renderer and story renderer must remain unchanged.
- Before edits, source files and their relevant hashes were saved in `review-history/2026-10-23-before-principles/`. Existing screenshots and the earlier verification report stay intact. New evidence receives principles-specific names.
- If later approved for the application, use a dedicated Vastu principles component/content/style owner connected to the existing service template and scene engine. Do not duplicate the route or transplant this standalone prototype as another application.
- No backend, provider, data, fee, availability, authentication, dependency, package, server contract, production source or publication action is part of this draft refinement.

## Verification

Compare hero/story source hashes and actual upper geometry at 1440×900 and 390×844 with the saved baseline. Inspect all three principles modes on desktop and phone, entry midpoint/settled states, keyboard focus, rapid changes, reduced motion, replay and 320px fitting. Count 81 grid cells by its 9-by-9 geometry and check the highlighted centre is the correct 3-by-3 region. Review the full page for length and balance. Run syntax/local-reference checks, update current review records, and preserve earlier proof with its original scope. No full website suite, deployment, real booking or physical-device acceptance is implied.
