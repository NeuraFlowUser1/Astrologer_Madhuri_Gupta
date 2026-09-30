"""Narrow transaction entry points for checkout lifecycle.

Callers authorize the receipt before using these internal methods. External
provider I/O starts only after start_order_creation's transaction has committed.
An uncertain commit must never be treated as permission to call the provider.
"""

import psycopg
from pathlib import Path
from psycopg.types.json import Jsonb

from .connection import StorageUnavailable, checked_config
from .models import BookingInput
from .security import receipt_digest, request_fingerprint


class Store:
    def __init__(self, dsn, *, expected_host):
        checked_config(dsn, expected_host)
        self._dsn = dsn
        self._expected_host = expected_host

    def _call(self, statement, parameters=()):
        try:
            checked_config(self._dsn, self._expected_host)
            with psycopg.connect(self._dsn, connect_timeout=8, prepare_threshold=None) as connection:
                connection.execute("SET LOCAL statement_timeout = '10s'")
                connection.execute("SET LOCAL lock_timeout = '5s'")
                result = connection.execute(statement, parameters).fetchone()[0]
            # Context manager commit completed before returning permission.
            return result
        except psycopg.Error:
            raise StorageUnavailable('Booking storage is temporarily unavailable.') from None

    def recovery_plan(self):
        return self._call((Path(__file__).parent/'queries/recovery_plan.sql').read_text())

    def claim_checkout_resume(self, booking_id):
        return self._call('SELECT sarsa_booking.claim_checkout_resume(%s)', (booking_id,))

    def checkout_launchable(self, booking_id):
        return self._call('''SELECT EXISTS(SELECT 1 FROM sarsa_booking.bookings b
            JOIN sarsa_booking.payment_orders p ON p.booking_id=b.id
            JOIN sarsa_booking.checkout_contexts c ON c.id=b.context_id
            WHERE b.id=%s AND b.state='held' AND b.hold_expires_at>clock_timestamp()
              AND c.active_checkout_id=b.id AND p.state='ready' AND p.resolved_at IS NULL
              AND EXISTS(SELECT 1 FROM sarsa_booking.slot_claims s WHERE s.booking_id=b.id
                AND s.released_at IS NULL AND s.starts_at=b.starts_at AND s.ends_at=b.ends_at)
              AND NOT EXISTS(SELECT 1 FROM sarsa_booking.payment_cases WHERE booking_id=b.id AND resolved_at IS NULL)
              AND NOT EXISTS(SELECT 1 FROM sarsa_booking.accepted_payments WHERE booking_id=b.id))''', (booking_id,))

    def expire_holds(self):
        return self._call('SELECT sarsa_booking.expire_holds()')

    def claim_email_delivery(self):
        return self._call('SELECT sarsa_booking.claim_email_delivery()')

    def begin_email_send(self, job, message, digest):
        return self._call('SELECT sarsa_booking.begin_email_send(%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],Jsonb(message),digest))

    def finish_email_delivery(self, job, provider, error, attention, delay):
        return self._call('SELECT sarsa_booking.finish_email_delivery(%s,%s,%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],provider,error,attention,delay))

    def reconcile_email_event(self):
        return self._call('SELECT sarsa_booking.reconcile_email_event()')

    def claim_google_refresh(self, role, client_id):
        return self._call('SELECT sarsa_booking.claim_google_refresh(%s,%s)', (role,client_id))

    def claim_google_delivery(self):
        return self._call('SELECT sarsa_booking.claim_google_delivery()')

    def finish_google_delivery(self, job, state, provider=None, meet=None, error=None, delay=15):
        return self._call('SELECT sarsa_booking.finish_google_delivery(%s,%s,%s,%s,%s,%s,%s)',
            (job['id'],job['lease_token'],state,provider,meet,error,delay))

    def claim_google_workbook(self, role, client_id):
        return self._call('SELECT sarsa_booking.claim_google_workbook(%s,%s)', (role,client_id))

    def finish_google_workbook(self, role, lease, file_id):
        return self._call('SELECT sarsa_booking.finish_google_workbook(%s,%s,%s)', (role,lease,file_id))

    def assign_sheet_row(self, role, job_id, values):
        return self._call('SELECT sarsa_booking.assign_sheet_row(%s,%s,%s)', (role,job_id,Jsonb(values)))

    def finish_google_refresh(self, role, client_id, subject, revision, lease, encrypted, expires):
        return self._call('SELECT sarsa_booking.finish_google_refresh(%s,%s,%s,%s,%s,%s,%s)',
                          (role,client_id,subject,revision,lease,encrypted,expires))

    def claim_enquiry_delivery(self, lane):
        return self._call('SELECT sarsa_booking.claim_enquiry_delivery(%s)', (lane,))

    def begin_enquiry_send(self, job, encrypted, digest):
        return self._call('SELECT sarsa_booking.begin_enquiry_send(%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],encrypted,digest))

    def finish_enquiry_delivery(self, job, provider, error, attention, delay):
        return self._call('SELECT sarsa_booking.finish_enquiry_delivery(%s,%s,%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],provider,error,attention,delay))

    def reconcile_enquiry_email_event(self):
        return self._call('SELECT sarsa_booking.reconcile_enquiry_email_event()')

    def assign_enquiry_row(self, role, job, values):
        return self._call('SELECT sarsa_booking.assign_enquiry_row(%s,%s,%s)', (role,job,Jsonb(values)))

    def start_enquiry(self, request_id, receipt, fingerprint, payload, digest, encrypted, email_key):
        return self._call('SELECT sarsa_booking.start_enquiry(%s,%s,%s,%s,%s,%s,%s)',
                         (request_id,receipt,fingerprint,Jsonb(payload),digest,encrypted,email_key))

    def enquiry_status(self, request_id, receipt):
        return self._call('SELECT sarsa_booking.enquiry_view(%s,%s)', (request_id,receipt))

    def enquiry_verification_context(self, request_id, receipt):
        return self._call("""SELECT (SELECT jsonb_build_object('email',payload->>'email','generation',generation)
            FROM sarsa_booking.enquiries WHERE request_id=%s AND receipt_digest=%s
              AND receipt_expires_at>clock_timestamp())""", (request_id,receipt))

    def resend_enquiry(self, request_id, receipt, operation, generation, digest, encrypted):
        return self._call('SELECT sarsa_booking.resend_enquiry(%s,%s,%s,%s,%s,%s)',
                         (request_id,receipt,operation,generation,digest,encrypted))

    def verify_enquiry(self, request_id, receipt, generation, digest):
        return self._call('SELECT sarsa_booking.verify_enquiry(%s,%s,%s,%s)',
                         (request_id,receipt,generation,digest))

    def expire_enquiry_codes(self):
        return self._call('SELECT sarsa_booking.expire_enquiry_codes()')

    def studio_inbox_list(self, session, client, origin, view, after):
        return self._call('SELECT sarsa_booking.studio_inbox_list(%s,%s,%s,%s,%s)',(session,client,origin,view,after))

    def studio_inbox_detail(self, session, client, origin, item):
        return self._call('SELECT sarsa_booking.studio_inbox_detail(%s,%s,%s,%s)',(session,client,origin,item))

    def studio_inbox_review(self, session, client, origin, operation, item, revision, note):
        return self._call('SELECT sarsa_booking.studio_inbox_review(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_support_change(self,session,client,origin,operation,reference,revision,action,reason,payment,email,phone,digest):
        return self._call('SELECT sarsa_booking.studio_support_change(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,reference,revision,action,reason,payment,email,phone,digest))

    def redeem_receipt_recovery(self,reference,code,digest):
        return self._call('SELECT sarsa_booking.redeem_receipt_recovery(%s,%s,%s)',(reference,code,digest))

    def studio_inbox_refund_verified(self,session,client,origin,operation,item,revision,note):
        return self._call('SELECT sarsa_booking.studio_inbox_refund_verified(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_inbox_retry(self,session,client,origin,operation,item,revision,note):
        return self._call('SELECT sarsa_booking.studio_inbox_retry(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_booking_lookup(self,session,client,origin,reference):
        return self._call('SELECT sarsa_booking.studio_booking_lookup(%s,%s,%s,%s)',(session,client,origin,reference))

    def studio_appointment_reschedule(self,session,client,origin,operation,claim,revision,reason,start):
        return self._call('SELECT sarsa_booking.studio_appointment_reschedule(%s,%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,claim,revision,reason,start))

    def studio_appointment_detail(self,session,client,origin,claim):
        return self._call('SELECT sarsa_booking.studio_appointment_detail(%s,%s,%s,%s)',(session,client,origin,claim))

    def studio_appointment_cancel(self,session,client,origin,operation,claim,revision,reason):
        return self._call('SELECT sarsa_booking.studio_appointment_cancel(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,claim,revision,reason))

    def studio_calendar_list(self, session, client, origin, day, after):
        return self._call('SELECT sarsa_booking.studio_calendar_list(%s,%s,%s,%s,%s)',
                         (session,client,origin,day,after))

    def studio_calendar_close(self, session, client, origin, operation, reason, start, end):
        return self._call('SELECT sarsa_booking.studio_calendar_close(%s,%s,%s,%s,%s,%s,%s)',
                         (session,client,origin,operation,reason,start,end))

    def studio_calendar_reopen(self, session, client, origin, operation, claim, reason):
        return self._call('SELECT sarsa_booking.studio_calendar_reopen(%s,%s,%s,%s,%s,%s)',
                         (session,client,origin,operation,claim,reason))

    def studio_session(self, digest, client_id, origin):
        return self._call('SELECT sarsa_booking.studio_session(%s,%s,%s)', (digest,client_id,origin))

    def start_google_attempt(self, state, browser, purpose, role, encrypted, session, client_id, origin):
        return self._call('SELECT sarsa_booking.start_google_attempt(%s,%s,%s,%s,%s,%s,%s,%s)',
                          (state,browser,purpose,role,encrypted,session,client_id,origin))

    def consume_google_attempt(self, state, browser, purpose, client_id, origin):
        return self._call('SELECT sarsa_booking.consume_google_attempt(%s,%s,%s,%s,%s)',
                          (state,browser,purpose,client_id,origin))

    def finish_google_signin(self, state, subject, digest):
        return self._call('SELECT sarsa_booking.finish_google_signin(%s,%s,%s)', (state,subject,digest))

    def finish_google_connection(self, state, subject, encrypted, expires):
        return self._call('SELECT sarsa_booking.finish_google_connection(%s,%s,%s,%s)',
                          (state,subject,encrypted,expires))

    def studio_logout(self, digest, client_id, origin):
        return self._call('SELECT sarsa_booking.studio_logout(%s,%s,%s)', (digest,client_id,origin))

    def studio_connection_status(self, digest, client_id, origin):
        # Recheck session at read time; never trust an earlier HTTP-layer check.
        return self._call('''SELECT (SELECT jsonb_build_object(
            'authorization_saved',g.role IS NOT NULL,
            'reconnect_required',coalesce(g.grant_expires_at<=clock_timestamp(),false),
            'workbook_id',(SELECT w.spreadsheet_id FROM sarsa_booking.google_workbooks w
              WHERE w.role=s.role AND w.subject=s.subject AND w.client_id=s.client_id AND w.state='ready'))
            FROM sarsa_booking.studio_sessions s LEFT JOIN sarsa_booking.google_connections g
              ON g.role=s.role AND g.subject=s.subject AND g.client_id=s.client_id
            WHERE s.digest=%s AND sarsa_booking.studio_session(s.digest,%s,%s) IS NOT NULL)''',
            (digest,client_id,origin))

    def start_order_creation(self, context_id, booking_id):
        return self._call('SELECT sarsa_booking.start_order_creation(%s,%s)', (context_id,booking_id))

    def abandon_unattempted(self, context_id, booking_id):
        return self._call('SELECT sarsa_booking.abandon_unattempted(%s,%s)', (context_id,booking_id))

    def reserve(self, context_id, draft, receipt_secret, receipt_key, expected_merchant=None):
        """Caller must authorize context and pass the outer abuse/readiness gates.

        Both transactions recompute the same normalized payload binding. A lost
        response/commit is retried with the SAME request and receipt. Never call
        a payment provider because a reservation commit was merely attempted.
        """
        draft = BookingInput.model_validate(draft)
        payload = draft.model_dump(mode='json')
        if payload.get('normalization_version') == 1:
            # Legacy fingerprints predate the explicit version field.
            payload.pop('normalization_version')
        digest = receipt_digest(draft.request_id, receipt_secret, receipt_key)
        fingerprint = request_fingerprint(payload)
        args = (context_id, draft.request_id, digest, fingerprint)
        admission = self._call('SELECT sarsa_booking.admit_checkout(%s,%s,%s,%s)', args)
        if admission not in ('pending', 'committed'):
            return {'code': admission}
        return self._call('SELECT sarsa_booking.reserve_configured_checkout(%s,%s,%s,%s,%s,%s)',
                          (*args, Jsonb(payload), Jsonb(expected_merchant) if expected_merchant is not None else None))

    def order_intent(self, context_id, booking_id):
        return self._call('''SELECT (SELECT jsonb_build_object(
            'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
            'amount_paise',b.amount_paise,'currency',b.currency)
            FROM sarsa_booking.bookings b JOIN sarsa_booking.payment_orders p ON p.booking_id=b.id
            WHERE b.id=%s AND b.context_id=%s)''', (booking_id,context_id))

    def record_order_creation(self, context_id, booking_id, intent, order_id):
        return self._call('SELECT sarsa_booking.record_order_creation(%s,%s,%s,%s,%s,%s)',
                         (context_id,booking_id,intent['merchant_id'],intent['mode'],
                          intent['credential_version'],order_id))

    def observe_payment(self, context_id, booking_id, intent, evidence):
        return self._call('SELECT sarsa_booking.observe_payment(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (context_id,booking_id,intent['merchant_id'],intent['mode'],
                          intent['credential_version'],evidence.id,evidence.order_id,evidence.digest,
                          evidence.status,evidence.amount,evidence.currency,evidence.amount_refunded,
                          evidence.captured))

    def receipt_snapshot(self, request_id):
        # File is application-owned SQL, not supplied by a request.
        from pathlib import Path
        sql = (Path(__file__).with_name('queries') / 'receipt_snapshot.sql').read_text()
        return self._call(sql, (request_id,))

    def payment_intake(self):
        return self._call("SELECT jsonb_build_object('merchant_id',merchant_id,'mode',payment_mode,'credential_version',credential_version) FROM sarsa_booking.intake_settings WHERE singleton")

    def scheduling_snapshot(self, start, end):
        return self._call('''WITH instant AS MATERIALIZED (SELECT clock_timestamp() AS at)
            SELECT jsonb_build_object('server_now',instant.at,
                'policy_version',s.policy_version,'public_open',s.public_open,'schedule_browsing_open',s.schedule_browsing_open,
                'specification',p.specification,
                'claims',coalesce((SELECT jsonb_agg(jsonb_build_object('starts_at',c.starts_at,'ends_at',c.ends_at))
                    FROM sarsa_booking.slot_claims c LEFT JOIN sarsa_booking.bookings b ON b.id=c.booking_id
                    WHERE c.released_at IS NULL AND c.starts_at<%s AND c.ends_at>%s
                      AND NOT coalesce(b.state='held' AND b.hold_expires_at<=instant.at,false)), '[]'::jsonb))
            FROM instant CROSS JOIN sarsa_booking.intake_settings s
              JOIN sarsa_booking.booking_policies p ON p.version=s.policy_version WHERE s.singleton''', (end,start))

    def context_snapshot(self, context_id):
        return self._call('''SELECT jsonb_build_object('server_now',clock_timestamp(),'context',
            (SELECT jsonb_build_object('credential_digest',credential_digest,'expires_at',expires_at)
             FROM sarsa_booking.checkout_contexts WHERE id=%s))''', (context_id,))

    def create_context(self, context_id, digest):
        return self._call('''WITH created AS (
            INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,expires_at)
            VALUES(%s,%s,clock_timestamp()+interval '24 hours') RETURNING expires_at
        ) SELECT expires_at FROM created''', (context_id,digest))

    def consume_limit(self, scope, digest):
        return self._call('SELECT sarsa_booking.consume_request_limit(%s,%s)', (scope,digest))

    def save_provider_event(self, provider, account, mode, event_id, body_hash, payload):
        # Acknowledgement is safe only after this transaction's commit returns.
        return self._call('''WITH inserted AS (
            INSERT INTO sarsa_booking.provider_inbox(provider,account_id,environment,event_id,body_hash,payload)
            VALUES(%s,%s,%s,%s,%s,%s)
            ON CONFLICT(provider,account_id,environment,event_id) DO UPDATE
              SET event_id=EXCLUDED.event_id
            RETURNING body_hash
        ) SELECT body_hash FROM inserted''', (provider,account,mode,event_id,body_hash,Jsonb(payload)))

    def claim_payment_recovery(self, limit=5):
        return self._call('SELECT sarsa_booking.claim_payment_recovery(%s)', (limit,))

    def finish_payment_recovery(self, job, delay, cursor, search_skip, error=None):
        return self._call('SELECT sarsa_booking.finish_payment_recovery(%s,%s,%s,%s,%s,%s)',
                         (job['booking_id'],job['lease_token'],delay,cursor,search_skip,error))

    def claim_payment_events(self, limit=5):
        return self._call('SELECT sarsa_booking.claim_payment_events(%s)', (limit,))

    def finish_payment_event(self, job, *, done, delay, error=None):
        return self._call('SELECT sarsa_booking.finish_payment_event(%s,%s,%s,%s,%s,%s,%s)',
                         (job['account_id'],job['environment'],job['event_id'],job['lease_token'],done,delay,error))

    def find_order(self, merchant_id, mode, provider_order_id):
        return self._call('''SELECT (SELECT jsonb_build_object('booking_id',b.id,'context_id',b.context_id,
            'merchant_id',p.merchant_id,'mode',p.mode,'credential_version',p.credential_version,
            'amount_paise',b.amount_paise,'currency',b.currency,'provider_order_id',p.provider_order_id)
            FROM sarsa_booking.payment_orders p JOIN sarsa_booking.bookings b ON b.id=p.booking_id
            WHERE p.merchant_id=%s AND p.mode=%s AND p.provider_order_id=%s)''',
                         (merchant_id,mode,provider_order_id))

    def wake_payment_recovery(self, booking_id):
        return self._call('''WITH changed AS (UPDATE sarsa_booking.payment_orders
            SET next_check_at=least(next_check_at,clock_timestamp()) WHERE booking_id=%s AND resolved_at IS NULL
            RETURNING booking_id) SELECT count(*) FROM changed''', (booking_id,))
