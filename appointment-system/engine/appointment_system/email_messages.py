"""Minimal version-one appointment emails from a saved delivery snapshot.

No notes, birth details, customer telephone or bearer receipt credentials enter
these messages. Frozen messages are reused by the dispatcher without rendering.
"""
import hashlib
import html
import json
import re
from uuid import UUID
from zoneinfo import ZoneInfo
from .configuration import label
from .mail_identity import tags_for

from .email_events import SENDER, PROJECT_TAG
from .resend_email import REPLY_TO, EmailFailure
from .receipt_view import timestamp


def message_hash(payload):
    return hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def render_message(job):
    try:
        job_id=str(UUID(job['id']))
        reference=str(UUID(job['payload']['reference']))
        data=job['payload']
        brand=label()
        kind,role=job['kind'],job['recipient_role']
        destination=job['destination']
        if role not in ('customer','client') or (role=='client' and destination!=REPLY_TO):
            raise ValueError()
        if kind=='payment_review' and role=='client':
            subject='A payment needs review — '+brand
            lines=['A payment needs your attention. This is not an appointment confirmation.',
                   'Booking reference: '+reference,'Open the private studio to review the payment.']
        elif kind=='booking_cancelled':
            subject='Appointment cancelled — '+brand
            lines=['This appointment has been cancelled.','Booking reference: '+reference,
                   'Cancellation does not confirm a refund. Please contact us about any refund due.']
        elif kind in ('booking_ack','booking_details') and (kind!='booking_details' or role=='customer'):
            zone=ZoneInfo(data['practice_timezone'])
            start=timestamp(data['starts_at']).astimezone(zone)
            time_label='India time' if zone.key=='Asia/Kolkata' else zone.key.rsplit('/',1)[-1].replace('_',' ')+' time ('+start.strftime('%Z')+')'
            meeting=data['meeting']
            if meeting not in ('internal','google_meet'):raise ValueError()
            amount=data['amount_paise']
            if type(amount) is not int or amount<=0 or data['currency']!='INR':raise ValueError()
            service=data['service']
            if not isinstance(service,str) or not 1<=len(service)<=200 or any(ord(c)<32 for c in service):raise ValueError()
            subject=('Your appointment details' if kind=='booking_details' else 'Appointment confirmed')+' — '+brand
            lines=['Your appointment is confirmed.' if role=='customer' else 'A paid appointment is confirmed.',
                   service,start.strftime('%d %B %Y at %I:%M %p')+' ('+time_label+')',
                   f'Amount: INR {amount//100:,}.{amount%100:02d}', 'Booking reference: '+reference]
            if kind=='booking_ack' and data.get('change_kind')=='rescheduled':
                subject='Appointment rescheduled — '+brand
                lines[0]='Your appointment has been moved to the time below.' if role=='customer' else 'An appointment has been rescheduled.'
                lines+=['This change does not request another payment.']
            if kind=='booking_ack' and data.get('change_kind')=='contact_corrected':
                subject='Appointment contact details updated — '+brand
                lines[0]=brand+' has updated the contact details for this appointment.'
                lines+=['Your appointment time and fee have not changed.']
            if kind=='booking_details':
                link=data['meet_url']
                if meeting!='google_meet' or not isinstance(link,str) or not re.fullmatch(r'https://meet\.google\.com/[a-z]{3}-[a-z]{4}-[a-z]{3}',link):raise ValueError()
                lines+=['Join your online appointment: '+link]
            elif role=='customer' and meeting=='google_meet':
                lines+=['Your meeting details will follow in a separate email.']
            elif role=='customer':lines+=['For meeting arrangements, reply to this email.']
            elif meeting=='internal':lines+=['Arrange this meeting directly with the customer. Open the private studio for the record.']
            else:lines+=['Open the private studio for the appointment record.']
        else:raise ValueError()
        lines+=['For help, reply to this email.',brand]
        return {'from':SENDER,'to':[destination],'reply_to':REPLY_TO,'subject':subject,
                'text':'\n\n'.join(lines),'html':'<!doctype html><html lang="en"><body>'+''.join('<p>'+html.escape(line)+'</p>' for line in lines)+'</body></html>',
                'tags':tags_for(job_id,job.get('template_version',1))}
    except (KeyError,TypeError,ValueError,AttributeError):
        raise EmailFailure('email_message_invalid',definitely_rejected=True) from None
