"""Durable contact HTTP contracts. Registered only with dedicated protection.

Contact's database switch defaults closed. Do not open it before delivery workers
and the production caller are wired and accepted; no legacy fallback is used.
"""
from fastapi import Request
from fastapi.responses import JSONResponse
from .access import AccessDenied
from .connection import StorageUnavailable
from .contact import EnquiryInput,EnquiryReference,EnquiryVerify,EnquiryResend,enquiry_payload,public_enquiry


def add_contact_routes(app,store,secrets,browser_request,limit,wake_publisher=None,*,delivery_ready=False):
    def credential(request,body,scope):
        browser_request(request)
        limit(request,scope)
        if secrets is None:raise StorageUnavailable()
        saved=store.enquiry_protection(body.request_id)
        value=request.headers.get('x-enquiry-receipt')
        if saved is None:
            try:saved={'receipt_format':'v1','receipt_key_id':secrets.receipt_keys.metadata(value)['key_id']}
            except ValueError:raise AccessDenied() from None
        return secrets.receipt(body.request_id,value,format=saved['receipt_format'],key_id=saved['receipt_key_id']),saved

    def outcome(result):
        try:public=public_enquiry(result)
        except ValueError:raise StorageUnavailable() from None
        code=public.get('code')
        if code=='access_unavailable':raise AccessDenied()
        errors={'request_conflict':409,'contact_unavailable':503,'invalid_request':422,'please_wait':429,
            'verification_limit':429,'verification_changed':409,'verification_expired':410,'verification_incorrect':422}
        if code in errors:
            return JSONResponse({'code':code},errors[code],headers={'Retry-After':'60'} if errors[code]==429 else None)
        if code!='ok' or public.get('state') not in ('awaiting_verification','expired','locked','received'):
            raise StorageUnavailable()
        return public

    def wake(result):
        # Publication must happen after the store call commits, including retries.
        if isinstance(result,dict) and result.get('code')=='ok' and wake_publisher is not None:
            wake_publisher.publish()
        return outcome(result)

    @app.post('/api/contact/start')
    def start(request:Request,body:EnquiryInput):
        receipt,protection=credential(request,body,'contact_start')
        if delivery_ready is not True:raise StorageUnavailable()
        payload,fingerprint=enquiry_payload(body)
        digest,encrypted=secrets.challenge(body.request_id,payload['email'],1)
        return wake(store.start_enquiry(body.request_id,receipt,fingerprint,payload,digest,encrypted,
                    secrets.digest('email-quota',payload['email'].casefold()),
                    protection['receipt_key_id'],secrets.digest_key.active))

    @app.post('/api/contact/status')
    def status(request:Request,body:EnquiryReference):
        receipt,_=credential(request,body,'contact_read')
        return outcome(store.enquiry_status(body.request_id,receipt))

    @app.post('/api/contact/resend')
    def resend(request:Request,body:EnquiryResend):
        receipt,_=credential(request,body,'contact_start')
        if delivery_ready is not True:raise StorageUnavailable()
        saved=store.enquiry_verification_context(body.request_id,receipt)
        if not isinstance(saved,dict):raise AccessDenied()
        generation=min(saved['generation']+1,3)
        digest,encrypted=secrets.challenge(body.request_id,saved['email'],generation)
        return wake(store.resend_enquiry(body.request_id,receipt,body.operation_id,generation,digest,encrypted,secrets.digest_key.active))

    @app.post('/api/contact/verify')
    def verify(request:Request,body:EnquiryVerify):
        receipt,_=credential(request,body,'contact_verify')
        saved=store.enquiry_verification_context(body.request_id,receipt)
        if not isinstance(saved,dict):raise AccessDenied()
        digest=secrets.digest('code',body.request_id,body.generation,saved['email'],body.code,
            key_id=saved['code_digest_key_id'],format=saved['code_digest_format'])
        return wake(store.verify_enquiry(body.request_id,receipt,body.generation,digest))

    @app.get('/api/contact/policy')
    def policy():
        if secrets is None:raise StorageUnavailable()
        return {'version':1,'receipt_key_id':secrets.digest_key.active}
