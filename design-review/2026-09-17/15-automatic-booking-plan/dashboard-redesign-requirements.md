# Deferred dashboard and date-selection redesign — owner direction, 30 September 2026

## Authority and sequence

Finish the current functional booking/provider/staff acceptance first. The owner explicitly deferred implementation of this redesign; this document records requirements, not permission to replace the UI now. The present two-owner setup screen exposed operational setup mechanics to client users and the date form requires users to know the appointment date in advance. Both fail the desired simple client experience.

## Design intent

Give Madhuri and her staff a compact Sarsa-only working screen where booked days and upcoming appointments are immediately discoverable. Make customer booking date/time choices easy to open and operate. NeuraFlow's separate permission and record-copy maintenance remain agency operations, without an agency account selector in the ordinary client flow.

## Required direction

- Client entry signs into the authorised Sarsa staff account without a competing NeuraFlow choice, role list or agency setup explanation. Keep staff/customer permissions and identities distinct; hiding an account choice must not grant extra access or expose an agency session.
- Move agency Google consent, workbook preparation and maintenance to a separately restricted administrative route. Existing saved agency consent and backend jobs can continue without showing an agency chooser to client staff. Google consent still requires the agency owner's real browser approval when needed; background code cannot invent or bypass that permission. Preserve separately owned Project004 workbooks and grants.
- This separation does not authorise removing truthful agency/data-processing disclosures from privacy notices or sharing account credentials. Audit all visible surfaces by audience; customer pages must not show internal setup mechanics.
- Staff dashboard opens with an actual calendar and clear date markers for booked days, plus a visible upcoming-appointments summary. Clicking a day updates the selected day's appointments in an adjacent panel on desktop and directly below on mobile. Include useful default selection, today/navigation, empty/loading/error states and accessible month controls. Do not require guessing a date to discover an appointment.
- Compact desktop shell: calendar/list and selected appointment details/actions in a single working view with modest scrolling where required. Separate setup/settings from routine appointments, inbox and support. Avoid vertically stacked operational sections and repeated jumps across the page. Mobile must reflow rather than shrinking all controls or clipping content.
- Customer and staff date/time selectors: the full visible control row opens the picker, not only the small native calendar icon. Provide clear date and time affordances, selected states, touch targets, keyboard/focus support and sensible availability feedback. Avoid inaccessible fake controls or date strings parsed according to ambiguous browser locale.
- Retain backend date/time/availability, quote consistency, session ownership, paid booking snapshot and atomic slot protections. Present India time clearly. Calendar markers must come from authoritative staff data with bounded paginated queries, not from loading every customer record or treating Google Calendar as an atomic second reservation system.
- Plan concrete layout/type/colour/component/state/motion values before implementation and create browsable HTML for review, with desktop/mobile screenshots and keyboard interaction checks. Multi-stage motion may support the experience; it must not slow booking or obscure controls.

## Current acceptance observation

Initial reads showed revision1 and no saved action; a later read and the owner's confirmation show the actual move saved at17:16:11.555 UTC, from2 October15:00 to16:00 India time. Revision2 is confirmed, the old slot is free and one new claim exists. Calendar, both record copies and three update emails completed. The earlier message request is superseded; do not infer a backend fault from a read made before a saved action was observed. The database functions retain the intended restricted security-definer boundary; absent direct runtime INSERT permission on staff history is expected. No permissions or booking rows were changed as a workaround.


## Review boundary

Each redesign requires its own Design Intent and Implementation Spec, planned API/data implications and rendered review before replacement. No source/frontend/backend/permissions/customer action changed by recording these requirements. Track future reuse in the004-to-003 improvement register after the design and implementation are actually selected; do not prematurely apply unreviewed redesign to Project003.
