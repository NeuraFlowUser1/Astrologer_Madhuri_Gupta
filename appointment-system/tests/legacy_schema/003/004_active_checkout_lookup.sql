CREATE INDEX bookings_active_email ON bookings(email) WHERE state = 'held';
