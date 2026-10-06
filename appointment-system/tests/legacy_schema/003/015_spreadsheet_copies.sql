-- Two independent Google Sheet mirrors are recoverable delivery work, not the
-- source of truth. Neon remains authoritative and a Sheet outage cannot undo
-- a saved inquiry or confirmed booking.
ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_jobs_kind_check;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_jobs_kind_check CHECK
    (kind IN ('booking_confirmed','booking_cancelled','payment_review','inquiry_received',
              'payment_event','sheet_booking','sheet_inquiry'));

ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_jobs_recipient_role_check;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_jobs_recipient_role_check
    CHECK (recipient_role IN ('calendar','customer','client','client_sheet','agency_sheet'));

ALTER TABLE delivery_jobs DROP CONSTRAINT delivery_recipient_required;
ALTER TABLE delivery_jobs ADD CONSTRAINT delivery_recipient_required CHECK (
    (kind='payment_event' AND recipient_role IS NULL) OR
    (kind='inquiry_received' AND recipient_role IN ('customer','client')) OR
    (kind IN ('booking_confirmed','booking_cancelled') AND recipient_role IN ('calendar','customer','client')) OR
    (kind='payment_review' AND recipient_role='client') OR
    (kind IN ('sheet_booking','sheet_inquiry') AND recipient_role IN ('client_sheet','agency_sheet'))
);
