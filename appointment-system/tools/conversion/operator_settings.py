"""Explicit handover selections; reuse the same protected readers as the runtime.

The selection document contains reader names, never key material. Every secret
comes from the installation-bound runtime configuration in the process only.
"""
from dataclasses import replace
from datetime import datetime,timezone
import re
from appointment_system.serialization import decode,object_fields,integer
from appointment_system.secret_configuration import booking_settings,ring
from appointment_system.payment_configuration import payment_accounts
from appointment_system.email_configuration import connection
from appointment_system.contact import ContactSecrets
from appointment_system.google_oauth import GrantCipher
from appointment_system.google_resources import Resources
from .records import Bindings
from .source import ConversionError,catalogue
from .handover import ROLE
from .mail import MailTransfer
from .transport import TransportTransfer
from .mail_events import MailEventTransfer
from .resources import ResourceTransfer
from .grants import GrantTransfer
from .recovery import RecoveryTransfer
from .support import SupportHistoryTransfer
from .allowance import AllowanceTransfer
from .configuration import ConfigurationTransfer
from .enquiry import EnquiryTransfer

def reader_name(value):
    return type(value) is str and value!='v1' and re.fullmatch(r'[a-z0-9][a-z0-9-]{0,63}',value) is not None


def receipt_kinds(layout):
    # Published 003/16 predates browser-owned checkout contexts. Do not invent
    # a historical key requirement for a credential that was never issued.
    kinds=('receipt','enquiry')
    if layout.schema+'.checkout_contexts' in layout.structure['relations']:
        kinds+=('context',)
    return kinds


def selections(raw,profile):
    value=decode(raw,maximum=16384)
    object_fields(value,{'version','installation_id','environment','source_layout','writer_roles',
                        'receipt_formats','recovery_reader','mail','google','enquiry_code_formats'})
    integer(value['version'],1,1)
    if (value['installation_id']!=profile.installation.installation_id
            or value['environment']!=profile.installation.document['environment']
            or value['source_layout'] not in ('legacy-003-16','legacy-004-31')):
        raise ConversionError('conversion_selection_identity_invalid')
    roles=value['writer_roles']
    if (type(roles) is not list or not 1<=len(roles)<=12
            or any(type(role) is not str or not ROLE.fullmatch(role) for role in roles)
            or len(set(roles))!=len(roles)):
        raise ConversionError('conversion_selection_writers_invalid')
    layout=next(item for item in catalogue() if item.identifier==value['source_layout'])
    expected={name+'-'+layout.project for name in receipt_kinds(layout)}
    if (type(value['receipt_formats']) is not dict or set(value['receipt_formats'])!=expected
            or any(not reader_name(name) for name in value['receipt_formats'].values())):
        raise ConversionError('conversion_selection_readers_invalid')
    if value['recovery_reader'] is not None and not reader_name(value['recovery_reader']):
        raise ConversionError('conversion_selection_readers_invalid')
    formats=value['enquiry_code_formats']
    if formats is not None and (layout.project!='004' or type(formats) is not list or len(formats)!=2
                                or any(not reader_name(name) for name in formats)):
        raise ConversionError('conversion_selection_readers_invalid')
    if value['mail'] is not None:
        object_fields(value['mail'],{'credential_version','contact_message_formats'})
        formats=value['mail']['contact_message_formats']
        if (type(value['mail']['credential_version']) is not str
                or formats is not None and (type(formats) is not list or len(formats)!=2
                                            or any(not reader_name(name) for name in formats))
                or layout.project=='003' and formats is not None):
            raise ConversionError('conversion_selection_readers_invalid')
    if value['google'] is not None:
        object_fields(value['google'],{'calendar_client','resource_formats','full_grant_reader'}, {'calendar_reauthorization'})
        google=value['google']
        if (google['calendar_client'] is not None and type(google['calendar_client']) is not str
                or type(google['resource_formats']) is not dict
                or any(type(key) is not str or not reader_name(name) for key,name in google['resource_formats'].items())
                or google['full_grant_reader'] is not None and not reader_name(google['full_grant_reader'])):
            raise ConversionError('conversion_selection_readers_invalid')
        reauthorization=google.get('calendar_reauthorization',False)
        if (type(reauthorization) is not bool or reauthorization and (
                layout.identifier!='legacy-003-16' or not google['calendar_client']
                or google['resource_formats'] or google['full_grant_reader'] is not None)):
            raise ConversionError('conversion_selection_reauthorization_invalid')
    return value


def bindings(profile,selection,environment,*,now=None):
    """No provider calls or database writes; unknown or missing readers fail closed."""
    project=selection['source_layout'].split('-')[1]
    booking=booking_settings(environment)
    contact=ContactSecrets.from_environment(environment)
    formats=selection['enquiry_code_formats']
    enquiry=EnquiryTransfer(contact,*formats) if formats is not None else None
    readers=selection['receipt_formats']
    layout=next(item for item in catalogue() if item.identifier==selection['source_layout'])
    expected={name+'-'+project for name in receipt_kinds(layout)}
    if set(readers)!=expected:
        raise ConversionError('conversion_selection_readers_invalid')
    for name,known in (('receipt',booking.receipt_key.legacy),('context',booking.context_key.legacy),
                       ('enquiry',contact.receipt_keys.legacy)):
        if name not in receipt_kinds(layout):continue
        if readers[name+'-'+project] not in known:
            raise ConversionError('conversion_reader_not_prepared')
    payments=payment_accounts(environment['BOOKING_RAZORPAY_ACCOUNTS'])
    base=Bindings(profile.installation,profile.initial_business,now or datetime.now(timezone.utc),
                  payment_readers=tuple(adapter.credentials for adapter in payments.versions.values()),
                  receipt_formats=readers)
    mail=None
    if selection['mail'] is not None:
        chosen=selection['mail'];formats=chosen['contact_message_formats']
        mail=MailTransfer(connection(environment['BOOKING_EMAIL_CONNECTION']),
                          {project:chosen['credential_version']},contact=contact,
                          contact_formats={project:tuple(formats)} if formats is not None else {})
    transport=TransportTransfer(base,mail)
    recovery=RecoveryTransfer(booking.receipt_key,selection['recovery_reader']) if selection['recovery_reader'] is not None else None
    history=SupportHistoryTransfer(recovery,MailEventTransfer(transport) if mail is not None else None)
    resource=None
    if selection['google'] is not None:
        chosen=selection['google'];resources=Resources.from_environment(environment);old_keys=()
        if chosen['full_grant_reader'] is not None:
            # Validate the complete existing protected document before selecting
            # its exact saved reader. No new key or alternate secret file exists.
            raw=environment['BOOKING_LEGACY_GOOGLE_GRANTS']
            legacy=decode(raw);name=chosen['full_grant_reader']
            reader=legacy.get('readers',{}).get(name)
            if (project!='004' or type(reader) is not dict
                    or reader.get('grant_purpose')!='sarsa:004:google-grant:v1'):
                raise ConversionError('conversion_resource_reader_invalid')
            client=chosen['calendar_client']
            GrantCipher(client,ring(environment,'BOOKING_GOOGLE_TOKEN_KEYS','google-grant'),raw)
            old_keys=tuple(reader['keys'])
        resource=ResourceTransfer(GrantTransfer(profile.installation,resources,old_keys=old_keys,
            calendar_client=chosen['calendar_client'],formats=chosen['resource_formats'],
            calendar_reauthorization=chosen.get('calendar_reauthorization',False)))
    return replace(base,receipt_formats=dict(base.receipt_formats),mail_mapper=mail,
                   transport_mapper=transport,history_mapper=history,resource_mapper=resource,
                   enquiry_mapper=enquiry,
                   quota_mapper=AllowanceTransfer(base) if project=='003' else ConfigurationTransfer())
