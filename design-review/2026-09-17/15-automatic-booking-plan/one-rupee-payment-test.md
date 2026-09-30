# Owner-authorised one-rupee live booking test — 30 September 2026

The owner explicitly selected a temporary reduced price of1 INR, using the normal completed booking journey rather than a mock payment or bypass. Change only Kundli Matching from210000 to100 paise. All other services,30-minute duration, Google Meet, schedule, mandatory contact details, hold/claim logic, merchant binding, payment verification and staff controls remain unchanged. The temporary price is publicly visible and purchasable while active; no private-only restriction is falsely implied.

## Prepared and checked

- Source: backend/booking_engine/policy.py uses100 paise for kundli-matching; frontend/src/site/catalogue.json is regenerated from that exact backend snapshot. Existing catalogue test reflects the explicitly approved temporary policy.
- Temporary quote version: e2df74043ffe3d4e5ca2e4b8bfcb44d4a5eb68ae0034b9ca7778ac67e0acaf0e.
- Original normal-price version retained:29824fcc90cabd9f8bd3245c787aa4b1694bd6270906fb65ba1eca3c2bd0fcd3.
- Inserted the immutable temporary snapshot in production and read back exact specification equality. The active database pointer still selects the original normal policy. Production has zero bookings at this checkpoint. No historical policy or customer/financial record was overwritten.
-244 fixture-based Python tests pass. The first restricted execution stalled and the interrupted process had no result; it is not counted as passed. The fresh complete suite outside that restriction passed244 in2.366 seconds. Frontend production build passed in2.13 seconds.

## Deployment and test sequence

1. Publish this reviewed change to the existing main branch, then the owner deploys main in the retained separate Vercel account. Codex must inspect live /api/booking-policy for the exact temporary version and100 paise before activation.
2. Compare-and-set the production intake_settings.policy_version from the exact original version to the exact prepared version. Assert the prepared snapshot still agrees with the reviewed source; retain all intake, merchant, protection, permission and quota values. Check public policy, availability and fresh checkout-context composition agree. During the short deployment/pointer transition, the existing version guard can reject fresh contexts; it must not accept mismatched pricing.
3. Owner refreshes /booking, selects Kundli Matching, chooses an available time with sufficient lead time for the planned support checks, enters their own accurate details and completes the actual1 INR Razorpay payment. No duplicate submission if the outcome is uncertain: use the saved receipt first.
4. Inspect the exact owner booking:100-paise order/payment in the bound merchant, verified capture, one appointment/slot, signed callbacks, confirmation, Google Meet, both Project004-owned record copies and emails. Inspect staff changes using this real appointment only; no unsolicited charge or refund is authorised by creating this test policy.
5. Promptly restore the normal service amount in policy.py and its catalogue test, regenerate the frontend catalogue, rerun the appropriate checks/build and publish/deploy. Restore the active database pointer to the original policy in coordination with that deployment. Recheck all four normal prices and normal-context admission. Existing test booking/payment snapshots remain100 paise and must never be rewritten to210000.

No automatic expiry is implemented: a concrete restore action remains mandatory. Keep this item open until normal source, deployment and database policy are restored and read back. New business-policy versions remain additive; never edit applied migration004 or its checksum merely to change a temporary price.
