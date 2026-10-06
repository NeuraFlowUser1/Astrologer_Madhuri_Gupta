-- Publication is separate from delivery. Never erase a job when a queue expires.
ALTER TABLE delivery_jobs ADD COLUMN dispatch_after timestamptz;
UPDATE delivery_jobs SET dispatch_after=created_at;
ALTER TABLE delivery_jobs ALTER COLUMN dispatch_after SET NOT NULL;
ALTER TABLE delivery_jobs ALTER COLUMN dispatch_after SET DEFAULT now();
ALTER TABLE delivery_jobs ADD COLUMN dispatch_token uuid;
ALTER TABLE delivery_jobs ADD COLUMN dispatched_at timestamptz;
ALTER TABLE delivery_jobs ADD COLUMN dispatch_attempts integer NOT NULL DEFAULT 0 CHECK (dispatch_attempts >= 0);
ALTER TABLE delivery_jobs ADD COLUMN dispatch_error text;
CREATE INDEX inquiry_dispatch_due ON delivery_jobs(dispatch_after,id)
    WHERE kind='inquiry_received' AND state IN ('pending','processing');
