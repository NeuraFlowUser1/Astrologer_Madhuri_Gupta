"""Synthetic process configuration for actual handover parsers; never a product default."""
import json
from appointment_system.configuration import installation
from appointment_system.keys import encode
from .test_application import environment,protection
from .test_mail_contracts import document as mail_document
from .test_conversion_grants import readers as resource_readers,KEY
from .test_google_resources import spec as resources,WEB


def selection(project):
    facts=installation()
    return dict(version=1,installation_id=facts['installation_id'],environment=facts['environment'],
        source_layout='legacy-'+project+('-16' if project=='003' else '-31'),
        writer_roles=['astro_booking_app' if project=='003' else 'sarsa_booking_web'],
        receipt_formats={name+'-'+project:'retained-'+name for name in
                         (('receipt','enquiry') if project=='003' else ('receipt','context','enquiry'))},
        recovery_reader=None,mail=None,google=None,enquiry_code_formats=None)


def protected(project,*,integrations=False):
    facts=installation();env=environment()
    base=dict(version=1,installation_id=facts['installation_id'],environment=facts['environment'])
    def reader(purpose,encoding):
        return dict(algorithm='json-sha256',audience='',purpose=purpose,key_id=None,encoding=encoding)
    env['BOOKING_LEGACY_PROTECTION']=json.dumps(base|dict(readers={
        'receipt':{'retained-receipt':reader('booking','hex64')},
        'context':{'retained-context':reader('context','uuid-hex64')|dict(algorithm='hmac-sha256',key_id='prior')},
        'recovery':{'retained-support':dict(key_id='prior',code_audience='sarsa:004:support-code:v1:',
                                          digest_audience='sarsa:004:support-code-digest:v1:')}},
        materials={'prior':encode(b'R'*32)}))
    env['BOOKING_ENQUIRY_DIGEST_KEYS']=json.dumps(protection('enquiry-digest',4))
    env['BOOKING_ENQUIRY_ENCRYPTION_KEYS']=json.dumps(protection('enquiry-encryption',5))
    env['BOOKING_LEGACY_ENQUIRY_PROTECTION']=json.dumps(base|dict(
        receipt_readers={'retained-enquiry':reader('inquiry','hex64')},materials={'digest':encode(b'D'*32)},
        cipher_readers={'old-message':dict(algorithm='fernet-json',keys=[KEY],purpose='sarsa004-contact-message-v1'),
                        'old-code':dict(algorithm='fernet-json',keys=[KEY],purpose='sarsa004-contact-code-v1')},
        digest_readers={'old-digest':dict(key_id='digest',audience='sarsa004')}))
    env['BOOKING_RAZORPAY_ACCOUNTS']=json.dumps(base|dict(provider='razorpay',active_account_version='old_v1',accounts=[
        dict(account_version='old_v1',merchant_id='merchant123',mode='test',key_id='rzp_test_legacy',
             key_secret='synthetic-secret-at-least-sixteen',state='active')]))
    selected=selection(project)
    if project=='004':selected['enquiry_code_formats']=['old-code','old-digest']
    if integrations:
        mail=mail_document();record=mail['legacy_identities'][0]
        record.update(format='resend-legacy-job-v1' if project=='003' else 'resend-legacy-flat-job-v1',
                      project='003-astroadvice-by-kundan-singh' if project=='003' else 'sarsa004',
                      sender='Historical Practice <old@example.com>',address='old@example.com',reply_to='practice@example.test')
        if project=='003':mail['legacy_identities'].append(record|{'format':'resend-legacy-untagged-job-v1'})
        env['BOOKING_EMAIL_CONNECTION']=json.dumps(mail)
        env['BOOKING_GOOGLE_RESOURCES']=json.dumps(resources())
        env['BOOKING_GOOGLE_RESOURCE_KEYS']=json.dumps(protection('google-resource-grant',6))
        env['BOOKING_GOOGLE_TOKEN_KEYS']=json.dumps(protection('google-grant',7))
        env['BOOKING_LEGACY_RESOURCE_READERS']=json.dumps(resource_readers())
        env['BOOKING_LEGACY_GOOGLE_GRANTS']=json.dumps(base|dict(purpose='google-grant',readers={
            'saved-full-grant':dict(algorithm='fernet-json',keys=[KEY],grant_purpose='sarsa:004:google-grant:v1',
                                   attempt_purpose='sarsa:004:google-attempt:v1')}))
        selected['mail']=dict(credential_version='k1',contact_message_formats=['old-message','old-digest'] if project=='004' else None)
        selected['google']=dict(calendar_client=WEB,
            resource_formats={'calendar-bound':'astro-calendar-bound','calendar-bare':'astro-calendar-bare'} if project=='003' else {},
            full_grant_reader='saved-full-grant' if project=='004' else None)
        selected['recovery_reader']='retained-support'
    return selected,env
