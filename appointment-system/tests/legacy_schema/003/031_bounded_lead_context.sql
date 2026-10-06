-- Finite source/service labels; saved request identities and old snapshots stay intact.
ALTER TABLE public.inquiries DROP CONSTRAINT inquiry_source;
ALTER TABLE public.inquiries ADD CONSTRAINT inquiry_source CHECK(source IN
 ('home','contact','prashna','service','booking','unknown'));
ALTER TABLE public.inquiries ADD COLUMN service_interest text;
ALTER TABLE public.inquiries ADD CONSTRAINT inquiry_service_interest CHECK(service_interest IS NULL OR
 service_interest IN ('vedic-astrology','numerology','vastu','laal-kitaab','prashna-kundali','name-change'));
