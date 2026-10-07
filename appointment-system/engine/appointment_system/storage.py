"""Narrow transaction entry points for checkout lifecycle.

Callers authorize the receipt before using these internal methods. External
provider I/O starts only after start_order_creation's transaction has committed.
An uncertain commit must never be treated as permission to call the provider.
"""

import psycopg
from pathlib import Path
from psycopg.types.json import Jsonb

from .connection import StorageUnavailable, checked_config
from .models import BookingInput,BookingRequest
from .security import receipt_digest, request_fingerprint


class UnavailableStore:
    """A missing purpose never borrows another purpose's database credential."""
    def __getattr__(self,name):
        if name.startswith('_'):raise AttributeError(name)
        def unavailable(*args,**kwargs):raise StorageUnavailable('This operation requires its own protected connection.')
        return unavailable


def _job(kind,job):
    from .job_authority import JobClaim
    return JobClaim.saved(kind,job)


class Store:
    def begin_recovery_run(self,run,release,scheduled):
        return self._call('SELECT appointment_system.begin_recovery_run(%s,%s,%s)',(run,release,scheduled))

    def claim_recovery_turn(self,run,lane,generation,release):
        return self._call('SELECT appointment_system.claim_recovery_turn(%s,%s,%s,%s)',(run,lane,generation,release))

    def complete_recovery_turn(self,run,lane,token,generation,release,processed,retry,attention):
        return self._call('SELECT appointment_system.complete_recovery_turn(%s,%s,%s,%s,%s,%s,%s,%s)',
                          (run,lane,token,generation,release,processed,retry,attention))

    def end_recovery_run(self,run,release):
        return self._call('SELECT appointment_system.finish_recovery_run(%s,%s)',(run,release))

    def claim_publication(self):
        return self._call('SELECT appointment_system.control_claim_publication()')

    def finish_publication(self,job,ack=None,error=None):
        return self._call('SELECT appointment_system.control_finish_publication(%s,%s,%s,%s)',
            (job['operation_id'],job['lease_token'],Jsonb(ack) if ack is not None else None,error))

    def claim_probe(self):
        return self._call('SELECT appointment_system.control_claim_probe()')

    def probe_retry(self,job,error):
        return self._call('SELECT appointment_system.control_probe_retry(%s,%s,%s)',
            (job['operation_id'],job['lease_token'],error))

    def record_probe(self,job,observed):
        return self._call('SELECT appointment_system.control_record_probe(%s,%s)',
            (job['operation_id'],Jsonb(observed)))
    def claim_financial_resources(self,merchant=None,mode=None):
        return self._call('SELECT appointment_system.claim_financial_resources(%s,%s,1)',(merchant,mode))

    def finish_financial_resource(self,job,delay,error=None):
        return self._call('SELECT appointment_system.finish_financial_resource(%s,%s,%s,%s)',
            (job['case_id'],job['lease_token'],delay,error))

    def __init__(self, dsn, *, expected_host,purpose="web"):
        checked_config(dsn, expected_host,purpose=purpose)
        self._dsn = dsn
        self._expected_host = expected_host
        self._purpose=purpose

    def _call(self, statement, parameters=(), *, diagnostic=False,job_authority=None):
        try:
            checked_config(self._dsn, self._expected_host,purpose=self._purpose)
            from .request_budget import BudgetCursor,remaining
            import certifi
            remaining(.5 if diagnostic else 3)
            transport={'sslmode':'verify-full','sslrootcert':certifi.where()}
            bounded={'connect_timeout':2,'tcp_user_timeout':2000,'keepalives_idle':2,'keepalives_interval':1,'keepalives_count':2} if diagnostic else {'connect_timeout':3}
            with psycopg.connect(self._dsn, cursor_factory=BudgetCursor,prepare_threshold=None,**bounded,**transport) as connection:
                connection.execute("SET LOCAL statement_timeout = '300ms'" if diagnostic else "SET LOCAL statement_timeout = '5s'")
                connection.execute("SET LOCAL lock_timeout = '100ms'" if diagnostic else "SET LOCAL lock_timeout = '2s'")
                from .configuration import installation
                facts=installation()
                matched=connection.execute("SELECT appointment_system.validate_caller(%s,%s,%s,%s)",
                     (facts["installation_id"],facts["environment"],self._purpose,1)).fetchone()[0]
                if matched is not True:
                    raise StorageUnavailable("This database does not match the declared installation and purpose.")
                from .worker_authority import current
                turn=current()
                if turn is not None and self._purpose=='worker':
                    connection.execute('SELECT appointment_system.require_worker_turn(%s,%s,%s,%s,%s)',turn.parameters())
                if job_authority is not None:
                    from .job_authority import JobClaim
                    if not isinstance(job_authority,JobClaim):raise ValueError('job_claim_invalid')
                    connection.execute('SELECT appointment_system.require_job_claim(%s,%s,%s,%s,%s,%s,%s,%s)',job_authority.parameters())
                result = connection.execute(statement, parameters).fetchone()[0]
                remaining(.1)
            # Context manager commit completed before returning permission.
            return result
        except psycopg.Error as error:
            if error.sqlstate in ('P0444','P0409'):
                from .service_control import ControlError
                raise ControlError('booking_disabled' if error.sqlstate=='P0444' else 'booking_activation_changed',
                                   404 if error.sqlstate=='P0444' else 409) from None
            raise StorageUnavailable('Booking storage is temporarily unavailable.') from None

    def require_booking_admission(self):
        return self._call('SELECT appointment_system.control_admission(NULL)')

    def record_operation_incident(self,reference,operation,stage,code,elapsed):
        return self._call('SELECT appointment_system.record_operation_incident(%s,%s,%s,%s,%s)',
            (reference,operation,stage,code,elapsed),diagnostic=True)




    def cleanup_temporary_records(self):
        return self._call('SELECT appointment_system.cleanup_temporary_records()')

    def claim_checkout_resume(self, booking_id):
        return self._call('SELECT appointment_system.claim_checkout_resume(%s)', (booking_id,))

    def finish_checkout_resume(self,job,delay,cursor,search_skip,error=None):
        return self._call('SELECT appointment_system.finish_checkout_resume(%s,%s,%s,%s,%s,%s)',
                         (job['booking_id'],job['lease_token'],delay,cursor,search_skip,error))

    def checkout_launchable(self, booking_id):
        return self._call('SELECT appointment_system.api_checkout_launchable(%s)', (booking_id,))

    def expire_holds(self):
        return self._call('SELECT appointment_system.expire_holds()')

    def claim_email_delivery(self):
        return self._call('SELECT appointment_system.claim_email_delivery()')

    def begin_email_send(self, job, message, digest,*,binding=None):
        if binding is not None:
            return self._call('SELECT appointment_system.begin_scoped_mail(%s,%s,%s,%s,%s,%s)',
                             ('booking',job['id'],job['lease_token'],Jsonb(message),digest,Jsonb(binding)),job_authority=_job('booking',job))
        return self._call('SELECT appointment_system.begin_email_send(%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],Jsonb(message),digest),job_authority=_job('booking',job))

    def finish_email_delivery(self, job, provider, error, attention, delay,*,rejected=False):
        return self._call('SELECT appointment_system.finish_mail_attempt(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         ('booking',job['id'],job['lease_token'],provider,job.get('message_hash'),error,attention,delay,rejected),job_authority=_job('booking',job))

    def mail_acceptance(self, kind, job):
        return self._call('SELECT appointment_system.adopt_mail_acceptance(%s,%s,%s)',(kind,job['id'],job['lease_token']))

    def reconcile_email_event(self):
        return self._call('SELECT appointment_system.reconcile_email_event()')


    def claim_google_resource_refresh(self,resource,grant_id=None):
        if grant_id is not None:
            return self._call('SELECT appointment_system.claim_google_resource_refresh(%s,%s)',(resource,grant_id))
        return self._call('SELECT appointment_system.claim_google_resource_refresh(%s)',(resource,))

    def finish_google_resource_refresh(self,saved,encrypted=None,expires=None,scopes=None,error=None):
        return self._call('SELECT appointment_system.finish_google_resource_refresh(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
            (saved['resource'],saved['grant_id'],saved['revision'],saved['resource_revision'],saved['lease'],
             encrypted,expires,Jsonb(scopes) if scopes is not None else None,error))

    def claim_google_delivery(self,resource=None):
        if resource is not None:
            return self._call('SELECT appointment_system.claim_google_resource(%s)',(resource,))
        return self._call('SELECT appointment_system.claim_google_delivery()')

    def finish_google_delivery(self, job, state, provider=None, meet=None, error=None, delay=15):
        return self._call('SELECT appointment_system.finish_google_delivery(%s,%s,%s,%s,%s,%s,%s)',
            (job['id'],job['lease_token'],state,provider,meet,error,delay),job_authority=_job('booking',job))

    def claim_google_workbook(self, role, client_id):
        return self._call('SELECT appointment_system.claim_google_workbook_v2(%s,%s)', (role,client_id))

    def begin_google_workbook_create(self, role, lease, intent):
        return self._call('SELECT appointment_system.begin_google_workbook_create(%s,%s,%s)', (role,lease,intent))

    def finish_google_workbook(self, role, lease, file_id):
        return self._call('SELECT appointment_system.finish_google_workbook(%s,%s,%s)', (role,lease,file_id))

    def mapped_google_row(self, role, job_id, kind):
        return self._call('SELECT appointment_system.mapped_google_row(%s,%s,%s)', (role,job_id,kind))

    def claim_sheet_projection(self, kind, role):
        return self._call('SELECT appointment_system.claim_sheet_projection(%s,%s)', (kind,role))

    def approve_sheet_projection(self, job, values, digest, observed):
        return self._call('SELECT appointment_system.approve_sheet_projection(%s,%s,%s,%s,%s,%s,%s,%s)',
            (job['role'],job['record_kind'],job['record_id'],job['lease'],job['sequence'],Jsonb(values),digest,observed))

    def finish_sheet_projection(self, job, digest, error, attention):
        return self._call('SELECT appointment_system.finish_sheet_projection(%s,%s,%s,%s,%s,%s,%s,%s)',
            (job['role'],job['record_kind'],job['record_id'],job['lease'],job['sequence'],digest,error,attention))

    def assign_sheet_row(self, role, job, values):
        return self._call('SELECT appointment_system.assign_sheet_row(%s,%s,%s,%s,%s)',
            (role,job['id'],job['lease_token'],job['attempts'],Jsonb(values)),job_authority=_job('booking',job))


    def claim_enquiry_delivery(self, lane):
        return self._call('SELECT appointment_system.claim_enquiry_delivery(%s)', (lane,))

    def begin_enquiry_send(self, job, encrypted, digest,*,binding=None):
        if binding is not None:
            return self._call('SELECT appointment_system.begin_scoped_contact_mail(%s,%s,%s,%s,%s,%s,%s,%s)',
                (job['id'],job['lease_token'],encrypted,digest,Jsonb(binding),job.get('observed_product_revision'),
                 job.get('observed_product_generation'),job.get('render_version')),job_authority=_job('contact',job))
        if 'render_version' in job:
            return self._call('SELECT appointment_system.begin_contact_send(%s,%s,%s,%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],encrypted,digest,job['observed_product_revision'],job['observed_product_generation'],job['render_version']),job_authority=_job('contact',job))
        return self._call('SELECT appointment_system.begin_enquiry_send(%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],encrypted,digest),job_authority=_job('contact',job))

    def finish_enquiry_delivery(self, job, provider, error, attention, delay,*,rejected=False):
        if job['kind'] in ('verification','acknowledgement','practice_notice'):
            return self._call('SELECT appointment_system.finish_mail_attempt(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         ('contact',job['id'],job['lease_token'],provider,job.get('message_digest'),error,attention,delay,rejected),job_authority=_job('contact',job))
        return self._call('SELECT appointment_system.finish_enquiry_delivery(%s,%s,%s,%s,%s,%s)',
                         (job['id'],job['lease_token'],provider,error,attention,delay),job_authority=_job('contact',job))

    def reconcile_enquiry_email_event(self):
        return self._call('SELECT appointment_system.reconcile_enquiry_email_event()')

    def assign_enquiry_row(self, role, job, values):
        return self._call('SELECT appointment_system.assign_enquiry_row(%s,%s,%s,%s,%s)',
            (role,job['id'],job['lease_token'],job['attempts'],Jsonb(values)),job_authority=_job('contact',job))

    def enquiry_protection(self,request_id):
        return self._call('SELECT appointment_system.api_enquiry_protection(%s)',(request_id,))

    def start_enquiry(self, request_id, receipt, fingerprint, payload, digest, encrypted, email_key,receipt_key,code_key):
        return self._call('SELECT appointment_system.api_start_enquiry(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (request_id,receipt,fingerprint,Jsonb(payload),digest,encrypted,email_key,receipt_key,code_key))

    def enquiry_status(self, request_id, receipt):
        return self._call('SELECT appointment_system.enquiry_view(%s,%s)', (request_id,receipt))

    def enquiry_verification_context(self, request_id, receipt):
        return self._call('SELECT appointment_system.api_enquiry_verification_context(%s,%s)', (request_id,receipt))

    def resend_enquiry(self, request_id, receipt, operation, generation, digest, encrypted,code_key):
        return self._call('SELECT appointment_system.api_resend_enquiry(%s,%s,%s,%s,%s,%s,%s)',
                         (request_id,receipt,operation,generation,digest,encrypted,code_key))

    def verify_enquiry(self, request_id, receipt, generation, digest):
        return self._call('SELECT appointment_system.verify_enquiry(%s,%s,%s,%s)',
                         (request_id,receipt,generation,digest))

    def expire_enquiry_codes(self):
        return self._call('SELECT appointment_system.expire_enquiry_codes()')

    def studio_inbox_list(self, session, client, origin, view, after):
        return self._call('SELECT appointment_system.studio_inbox_list(%s,%s,%s,%s,%s)',(session,client,origin,view,after))

    def studio_inbox_detail(self, session, client, origin, item):
        return self._call('SELECT appointment_system.studio_inbox_detail(%s,%s,%s,%s)',(session,client,origin,item))

    def studio_inbox_review(self, session, client, origin, operation, item, revision, note):
        return self._call('SELECT appointment_system.studio_inbox_review(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_support_change(self,session,client,origin,operation,reference,revision,action,reason,payment,email,phone,digest,code_key):
        return self._call('SELECT appointment_system.studio_support_change(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,reference,revision,action,reason,payment,email,phone,digest,code_key))

    def recovery_protection(self,reference,operation=None):
        return self._call('SELECT appointment_system.recovery_protection(%s,%s)',(reference,operation))

    def redeem_receipt_recovery(self,reference,code,digest,receipt_key):
        return self._call('SELECT appointment_system.redeem_receipt_recovery(%s,%s,%s,%s)',(reference,code,digest,receipt_key))

    def studio_inbox_refund_verified(self,session,client,origin,operation,item,revision,note):
        return self._call('SELECT appointment_system.studio_inbox_refund_verified(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_inbox_resource_reviewed(self,session,client,origin,operation,item,revision,note):
        return self._call('SELECT appointment_system.studio_inbox_resource_reviewed(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_inbox_retry(self,session,client,origin,operation,item,revision,note):
        return self._call('SELECT appointment_system.studio_inbox_retry(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,item,revision,note))

    def studio_booking_lookup(self,session,client,origin,reference):
        return self._call('SELECT appointment_system.studio_booking_lookup(%s,%s,%s,%s)',(session,client,origin,reference))

    def studio_time_context(self,session,client,origin):
        return self._call('SELECT appointment_system.studio_time_context(%s,%s,%s)',(session,client,origin))

    def studio_resolve_time(self,session,client,origin,local,zone):
        return self._call('SELECT appointment_system.studio_resolve_time(%s,%s,%s,%s,%s)',(session,client,origin,local,zone))

    def studio_pending_result(self,session,client,origin,operation,purpose):
        return self._call('SELECT appointment_system.studio_pending_result(%s,%s,%s,%s,%s)',(session,client,origin,operation,purpose))

    def studio_action_result(self,session,client,origin,operation):
        return self._call('SELECT appointment_system.studio_action_result(%s,%s,%s,%s)',(session,client,origin,operation))

    def studio_appointment_reschedule(self,session,client,origin,operation,claim,revision,reason,start):
        return self._call('SELECT appointment_system.studio_appointment_reschedule(%s,%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,claim,revision,reason,start))

    def studio_appointment_detail(self,session,client,origin,claim):
        return self._call('SELECT appointment_system.studio_appointment_detail(%s,%s,%s,%s)',(session,client,origin,claim))

    def studio_appointment_cancel(self,session,client,origin,operation,claim,revision,reason):
        return self._call('SELECT appointment_system.studio_appointment_cancel(%s,%s,%s,%s,%s,%s,%s)',(session,client,origin,operation,claim,revision,reason))

    def studio_calendar_list(self, session, client, origin, day, after):
        return self._call('SELECT appointment_system.studio_calendar_list(%s,%s,%s,%s,%s)',
                         (session,client,origin,day,after))

    def studio_calendar_month(self,session,client,origin,month):
        return self._call('SELECT appointment_system.studio_calendar_month(%s,%s,%s,%s)',(session,client,origin,month))

    def studio_calendar_close(self, session, client, origin, operation, reason, start, end):
        return self._call('SELECT appointment_system.studio_calendar_close(%s,%s,%s,%s,%s,%s,%s)',
                         (session,client,origin,operation,reason,start,end))

    def studio_calendar_reopen(self, session, client, origin, operation, claim, reason):
        return self._call('SELECT appointment_system.studio_calendar_reopen(%s,%s,%s,%s,%s,%s)',
                         (session,client,origin,operation,claim,reason))

    def studio_session(self, digest, client_id, origin):
        return self._call('SELECT appointment_system.studio_session(%s,%s,%s)', (digest,client_id,origin))

    def start_google_attempt(self, state, browser, purpose, role, encrypted, session, client_id, origin,portal='booking'):
        return self._call('SELECT appointment_system.staff_signin_start(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                          (state,browser,purpose,role,encrypted,session,client_id,origin,portal))

    def consume_google_attempt(self, state, browser, purpose, client_id, origin):
        return self._call('SELECT appointment_system.staff_signin_consume(%s,%s,%s,%s,%s)',
                          (state,browser,purpose,client_id,origin))

    def finish_google_signin(self, state, subject, digest):
        return self._call('SELECT appointment_system.staff_signin_finish(%s,%s,%s)', (state,subject,digest))


    def studio_logout(self, digest, client_id, origin):
        return self._call('SELECT appointment_system.studio_logout(%s,%s,%s)', (digest,client_id,origin))


    def start_order_creation(self, context_id, booking_id):
        return self._call('SELECT appointment_system.start_order_creation(%s,%s)', (context_id,booking_id))

    def abandon_unattempted(self, context_id, booking_id):
        return self._call('SELECT appointment_system.abandon_unattempted(%s,%s)', (context_id,booking_id))

    def reserve(self, context_id, draft, receipt_secret, receipt_key, expected_merchant=None,*,verification_keys=None):
        """Caller must authorize context and pass the outer abuse/readiness gates.

        Both transactions recompute the same normalized payload binding. A lost
        response/commit is retried with the SAME request and receipt. Never call
        a payment provider because a reservation commit was merely attempted.
        """
        draft = BookingRequest.model_validate(draft)
        payload = draft.model_dump(mode='json')
        if payload.get('normalization_version') == 1:
            # Legacy fingerprints predate the explicit version field.
            payload.pop('normalization_version')
        from .credentials import ReceiptKeys
        if not isinstance(receipt_key,ReceiptKeys):raise ValueError('Declared receipt protection is required.')
        metadata=receipt_key.metadata(receipt_secret)
        payload["_receipt"]={"format":metadata["format"],"key_id":metadata["key_id"]}
        if payload.get('verification_grant') is not None:
            if verification_keys is None:raise StorageUnavailable('Booking verification is unavailable.')
            payload['verification_grant']=verification_keys.grant(payload['verification_grant'],context_id,payload['email'])
        digest = receipt_digest(draft.request_id, receipt_secret, receipt_key)
        fingerprint = request_fingerprint(payload)
        args = (context_id, draft.request_id, digest, fingerprint)
        admission = self._call('SELECT appointment_system.admit_checkout(%s,%s,%s,%s)', args)
        if admission not in ('pending', 'committed'):
            return {'code': admission}
        return self._call('SELECT appointment_system.reserve_configured_checkout(%s,%s,%s,%s,%s,%s)',
                          (*args, Jsonb(payload), Jsonb(expected_merchant) if expected_merchant is not None else None))

    def request_receipt_copy(self,request_id,receipt_secret,receipt_key,operation_id,revision,email,*,sending_ready):
        digest=receipt_digest(request_id,receipt_secret,receipt_key)
        return self._call('SELECT appointment_system.request_receipt_copy(%s,%s,%s,%s,%s)',
                         (request_id,digest,operation_id,revision,Jsonb({'email':email,'sending_ready':sending_ready})))

    def start_booking_verification(self,context,operation,email,digest,cipher,recipient,key):
        return self._call('SELECT appointment_system.start_booking_verification(%s,%s,%s,%s,%s,%s,%s)',
                          (context,operation,email,digest,cipher,recipient,key))

    def resend_booking_verification(self,context,operation,challenge,email,generation,digest,cipher,key):
        return self._call('SELECT appointment_system.resend_booking_verification(%s,%s,%s,%s,%s,%s,%s,%s)',
                          (context,operation,challenge,email,generation,digest,cipher,key))

    def booking_verification_metadata(self,context,challenge,email):
        return self._call('SELECT appointment_system.booking_verification_metadata(%s,%s,%s)',(context,challenge,email))

    def verify_booking_code(self,context,operation,challenge,email,generation,digest,grant,cipher):
        return self._call('SELECT appointment_system.verify_booking_code(%s,%s,%s,%s,%s,%s,%s,%s)',
                          (context,operation,challenge,email,generation,digest,grant,cipher))

    def claim_booking_code(self,job=None):
        return self._call('SELECT appointment_system.claim_booking_code(%s)',(job,))

    def begin_booking_code(self,job,cipher,digest,binding):
        return self._call('SELECT appointment_system.begin_booking_code(%s,%s,%s,%s,%s)',
                          (job['id'],job['lease_token'],cipher,digest,Jsonb(binding)),job_authority=_job('booking_code',job))

    def finish_booking_code(self,job,provider,error,review,delay,rejected):
        return self._call('SELECT appointment_system.finish_booking_code(%s,%s,%s,%s,%s,%s,%s)',
                          (job['id'],job['lease_token'],provider,error,review,delay,rejected),job_authority=_job('booking_code',job))

    def reconcile_booking_code_email_event(self):
        return self._call('SELECT appointment_system.reconcile_booking_code_email_event()')

    def order_intent(self, context_id, booking_id):
        return self._call('SELECT appointment_system.api_order_intent(%s,%s)', (booking_id,context_id))

    def record_order_creation(self, context_id, booking_id, intent, order_id):
        return self._call('SELECT appointment_system.record_order_creation(%s,%s,%s,%s,%s,%s)',
                         (context_id,booking_id,intent['merchant_id'],intent['mode'],
                          intent['credential_version'],order_id))

    def observe_payment(self, context_id, booking_id, intent, evidence):
        return self._call('SELECT appointment_system.observe_payment(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                         (context_id,booking_id,intent['merchant_id'],intent['mode'],
                          intent['credential_version'],evidence.id,evidence.order_id,evidence.digest,
                          evidence.status,evidence.amount,evidence.currency,evidence.amount_refunded,
                          evidence.captured))

    def observe_financial_resource(self, booking_id, intent, fact, provenance, evidence_hash, parent):
        return self._call('SELECT appointment_system.observe_financial_resource(%s,%s,%s,%s,%s,%s,%s,%s)',
            (booking_id,intent['merchant_id'],intent['mode'],intent['credential_version'],Jsonb(fact),provenance,evidence_hash,Jsonb(parent)))

    def receipt_snapshot(self, request_id):
        # Only the declared purpose-limited database entry can expose a receipt.
        return self._call('SELECT appointment_system.api_receipt_snapshot(%s)', (request_id,))

    def payment_intake(self):
        return self._call('SELECT appointment_system.api_payment_intake()')

    def public_policy(self):
        return self._call('SELECT appointment_system.public_policy()')

    def available_times(self, service_id, day, questions=1):
        return self._call('SELECT appointment_system.available_times(%s,%s,%s)', (service_id,day,questions))

    def scheduling_snapshot(self, start, end):
        return self._call('SELECT appointment_system.api_scheduling_snapshot(%s,%s)', (end,start))

    def context_snapshot(self, context_id):
        return self._call('SELECT appointment_system.api_context_snapshot(%s)', (context_id,))

    def create_context(self, context_id, digest,*,metadata=None):
        if metadata is not None:
            return self._call('SELECT appointment_system.api_create_context(%s,%s,%s,%s)',
                (context_id,digest,metadata["format"],metadata["key_id"]))
        return self._call('SELECT appointment_system.api_create_context(%s,%s)', (context_id,digest))

    def consume_limit(self, scope, digest, *, booking=False):
        if booking:
            # Admit the public booking read and commit its quota in one
            # restricted transaction. CASE forces admission before the write;
            # the normal contact/receipt/support quotas remain independent.
            return self._call('SELECT appointment_system.api_consume_limit(%s,%s)', (scope,digest))
        return self._call('SELECT appointment_system.consume_request_limit(%s,%s)', (scope,digest))

    def save_provider_event(self, provider, account, mode, event_id, body_hash, payload):
        # Acknowledgement is safe only after this transaction's commit returns.
        return self._call('SELECT appointment_system.api_save_provider_event(%s,%s,%s,%s,%s,%s)', (provider,account,mode,event_id,body_hash,Jsonb(payload)))

    def claim_payment_recovery(self, limit=5):
        return self._call('SELECT appointment_system.claim_payment_recovery(%s)', (limit,))

    def advance_order_search(self,job,candidates,complete):
        return self._call('SELECT appointment_system.advance_order_search(%s,%s,%s,%s,%s)',
            (job['booking_id'],job['lease_token'],job['order_search_skip'],candidates,complete))

    def finish_payment_recovery(self, job, delay, cursor, search_skip, error=None):
        return self._call('SELECT appointment_system.finish_payment_recovery(%s,%s,%s,%s,%s,%s)',
                         (job['booking_id'],job['lease_token'],delay,cursor,search_skip,error))

    def claim_payment_events(self, limit=5):
        return self._call('SELECT appointment_system.claim_payment_events(%s)', (limit,))

    def finish_payment_event(self, job, *, done, delay, error=None):
        return self._call('SELECT appointment_system.finish_payment_event(%s,%s,%s,%s,%s,%s,%s)',
                         (job['account_id'],job['environment'],job['event_id'],job['lease_token'],done,delay,error))

    def find_order(self, merchant_id, mode, provider_order_id):
        return self._call('SELECT appointment_system.api_find_order(%s,%s,%s)',
                         (merchant_id,mode,provider_order_id))

    def wake_payment_recovery(self, booking_id):
        return self._call('SELECT appointment_system.api_wake_payment_recovery(%s)', (booking_id,))
