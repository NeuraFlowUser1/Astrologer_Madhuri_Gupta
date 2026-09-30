"""Full HTTP/browser fixture in an explicitly owned, loopback-only test database.

The sole provider substitute is Google sign-in's identity response. The actual
browser-bound attempts, sessions, authorization, SQL support actions and receipt
redemption run unchanged. No production setting can activate this fixture.
"""
from datetime import datetime,timedelta,timezone
import json
import subprocess
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4
from types import SimpleNamespace
import psycopg
import httpx
from psycopg import sql
from cryptography.fernet import Fernet
from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.google_oauth import GrantCipher,SIGN_IN_CALLBACK,Grant,Access,OWNERS,scopes_for
from backend.booking_engine.studio import StudioServices
from backend.booking_engine.storage import Store
from backend.booking_engine.security import receipt_digest
from backend.booking_engine.policy import IST,policy_version

ROOT=Path('/tmp/sarsa-completion-check')
ORIGIN='https://localhost:3039'
CLIENT='100-completion.apps.googleusercontent.com'
SETTINGS=Settings(ORIGIN,b'a'*32,b'b'*32,b'c'*32)


def local_config():
    value=json.loads((ROOT/'local.json').read_text())
    if (not value['name'].startswith('sarsa-004-completion-') or value['port']!=25434
            or len(value['owner'])!=32 or not value.get('password')):
        raise RuntimeError('Refusing a database outside the owned local fixture.')
    identity=subprocess.run(['docker','inspect','--format','{{index .Config.Labels "sarsa.completion"}}',value['name']],
        stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,timeout=10,check=False)
    if identity.returncode or identity.stdout.strip()!=value['owner']:
        raise RuntimeError('Refusing a database without the exact owned test-container label.')
    return value


def owner():
    value=local_config()
    return psycopg.connect(host='127.0.0.1',port=value['port'],user='postgres',password=value['password'],
                          dbname='neondb',sslmode='require')


class SyntheticGoogleIdentity:
    settings=SimpleNamespace(client_id=CLIENT,origin=ORIGIN)

    def authorization_url(self,attempt,*,signin=False):
        if not signin:raise RuntimeError('This fixture does not request real Google permissions.')
        return 'https://accounts.google.com/o/oauth2/v2/auth?'+urlencode({
            'state':attempt.state,'login_hint':attempt.role,'redirect_uri':ORIGIN+SIGN_IN_CALLBACK})

    def sign_in(self,attempt,code):
        if code!='synthetic-'+attempt.role:raise RuntimeError('Synthetic identity mismatch.')
        return 'synthetic-completion-'+attempt.role


def prepare():
    value=local_config();web_password=Fernet.generate_key().decode()
    credentials=ROOT/'web.json';credentials.write_text(json.dumps({'password':web_password}));credentials.chmod(0o600)
    with owner() as connection:
        connection.execute(sql.SQL('ALTER ROLE sarsa_booking_web PASSWORD {}').format(sql.Literal(web_password)))
        if connection.execute('SELECT count(*) FROM sarsa_booking.bookings').fetchone()[0]:
            raise RuntimeError('Fixture is not empty; refusing to overwrite any existing record.')
        connection.execute('UPDATE sarsa_booking.email_policy SET daily_limit=20,monthly_limit=600,contact_daily_limit=8,contact_monthly_limit=240 WHERE id=true')
        day=datetime.now(IST).date()+timedelta(days=3)
        while day.weekday()==6:day+=timedelta(days=1)
        start=datetime.combine(day,datetime.min.time(),IST).replace(hour=10)
        fixtures=[]
        for index,kind in enumerate(('receipt','correction')):
            reference=uuid4();booking=uuid4();context=uuid4();claim=uuid4();observation=uuid4()
            at=start+timedelta(minutes=30*index);secret=('A' if index==0 else 'B')*43
            digest=receipt_digest(reference,secret,SETTINGS.receipt_key)
            connection.execute("INSERT INTO sarsa_booking.checkout_contexts(id,credential_digest,expires_at) VALUES(%s,%s,clock_timestamp()+interval '1 day')",(context,uuid4().hex*2))
            connection.execute('INSERT INTO sarsa_booking.checkout_admissions(request_id,context_id,receipt_digest,request_fingerprint) VALUES(%s,%s,%s,%s)',(reference,context,digest,'d'*64))
            connection.execute("""INSERT INTO sarsa_booking.bookings(id,request_id,context_id,state,service_id,policy_version,
                service_snapshot,amount_paise,currency,starts_at,ends_at,practice_timezone,full_name,email,phone,
                hold_expires_at,receipt_expires_at) VALUES(%s,%s,%s,'confirmed','kundli-prediction',%s,
                '{"name":"Synthetic support consultation"}',100,'INR',%s,%s,'Asia/Kolkata',
                'Synthetic Support Test','no-send@example.com','+919876543210',clock_timestamp()+interval '10 minutes',%s)""",
                (booking,reference,context,policy_version(),at,at+timedelta(minutes=30),at+timedelta(days=1)))
            connection.execute('INSERT INTO sarsa_booking.slot_claims(id,booking_id,starts_at,ends_at) VALUES(%s,%s,%s,%s)',(claim,booking,at,at+timedelta(minutes=30)))
            payment='pay_support'+str(index)
            connection.execute("""INSERT INTO sarsa_booking.payment_orders(booking_id,merchant_id,mode,credential_version,
                provider_order_id,state,attempted_at,resolution,resolved_at) VALUES(%s,'SyntheticMerchant','live',
                'fixture',%s,'ready',clock_timestamp(),'confirmed',clock_timestamp())""",(booking,'order_support'+str(index)))
            connection.execute("""INSERT INTO sarsa_booking.payment_observations(id,booking_id,merchant_id,mode,payment_id,
                provider_order_id,evidence_hash,status,amount_paise,currency,captured)
                VALUES(%s,%s,'SyntheticMerchant','live',%s,%s,%s,'captured',100,'INR',true)""",
                (observation,booking,payment,'order_support'+str(index),'e'*64))
            connection.execute("INSERT INTO sarsa_booking.accepted_payments(booking_id,observation_id,merchant_id,mode,payment_id) VALUES(%s,%s,'SyntheticMerchant','live',%s)",(booking,observation,payment))
            fixtures.append({'kind':kind,'reference':str(reference),'booking':str(booking),'claim':str(claim),
                             'payment':payment,'old_secret':secret})
    (ROOT/'fixtures.json').write_text(json.dumps({'day':str(day),'fixtures':fixtures},indent=2))
    print('Two synthetic confirmed appointments prepared. No payment or real provider was contacted.')


def make_app():
    value=local_config();web=json.loads((ROOT/'web.json').read_text())
    dsn=psycopg.conninfo.make_conninfo(host='127.0.0.1',port=value['port'],user='sarsa_booking_web',
                                    password=web['password'],dbname='neondb',sslmode='require')
    store=Store(dsn,expected_host='127.0.0.1')
    services=StudioServices(SyntheticGoogleIdentity(),GrantCipher(CLIENT,[Fernet.generate_key()]),b'd'*32)
    return create_application(store,SETTINGS,verified_client_address=lambda request:request.client.host,
                              studio_services=services)


def verify():
    fixture=json.loads((ROOT/'fixtures.json').read_text());rows=[]
    with owner() as connection:
        for item in fixture['fixtures']:
            row=connection.execute('SELECT state,revision,email,phone,receipt_revoked_at FROM sarsa_booking.bookings WHERE id=%s',(item['booking'],)).fetchone()
            assert row[0]=='confirmed' and row[4] is None,'Booking or recovered access changed unexpectedly.'
            if item['kind']=='correction':
                assert row[1:4]==(2,'corrected@example.com','+919876543211'),'Corrected contacts not saved.'
                jobs=connection.execute('SELECT kind,recipient_role,booking_revision FROM sarsa_booking.delivery_jobs WHERE booking_id=%s',(item['booking'],)).fetchall()
                expected={('booking_calendar','calendar',2),('booking_cancelled','calendar',1),
                    ('booking_ack','client',2),('booking_ack','customer',2),
                    ('sheet_booking','client_sheet',2),('sheet_booking','agency_sheet',2)}
                assert len(jobs)==6 and set(jobs)==expected,'New-revision work or old-meeting cleanup not queued exactly once.'
            else:assert row[1]==1,'Receipt replacement unexpectedly revised the appointment.'
            assert connection.execute('SELECT count(*) FROM sarsa_booking.slot_claims WHERE booking_id=%s AND released_at IS NULL',(item['booking'],)).fetchone()[0]==1,'Support action changed slot capacity.'
            assert connection.execute('SELECT count(*) FROM sarsa_booking.receipt_recoveries WHERE request_id=%s AND redeemed_at IS NOT NULL',(item['reference'],)).fetchone()[0]>=1,'Recovery was not redeemed.'
            rows.append(item['kind'])
        actions=dict(connection.execute('SELECT action,count(*) FROM sarsa_booking.staff_calendar_actions GROUP BY action').fetchall())
        assert actions=={'close':1,'reopen':1},'Calendar actions missing or duplicated.'
        assert connection.execute("SELECT count(*) FROM sarsa_booking.studio_audit WHERE action='signin'").fetchone()[0]>=1,'Actual sign-in state machine not exercised.'
    print('Full browser journeys verified against committed SQL: '+', '.join(rows)+' and blocked-time reopening.')


def deliveries():
    """Exercise real durable consumers, capturing all external requests locally."""
    from backend.booking_engine.google_delivery import run_google_delivery_once
    from backend.booking_engine.email_delivery import run_email_delivery_once
    from backend.booking_engine.google_workspace import CALENDAR,DRIVE,SHEETS,event_id
    from backend.booking_engine.resend_email import ResendSender
    value=local_config();web=json.loads((ROOT/'web.json').read_text())
    store=Store(psycopg.conninfo.make_conninfo(host='127.0.0.1',port=value['port'],user='sarsa_booking_web',
        password=web['password'],dbname='neondb',sslmode='require'),expected_host='127.0.0.1')
    cipher=GrantCipher(CLIENT,[Fernet.generate_key()])
    intents={};files={};rows={};events={};mail=[];mutations=[]
    class Google:
        settings=SimpleNamespace(client_id=CLIENT)
        def refresh(self,grant,*,now):
            return Access('synthetic-'+grant.role,now+timedelta(hours=1),grant)
    services=StudioServices(Google(),cipher,b'd'*32)
    with owner() as connection:
        for role,email in OWNERS.items():
            subject='synthetic-completion-'+role
            connection.execute('INSERT INTO sarsa_booking.studio_identities(role,subject) VALUES(%s,%s) ON CONFLICT(role) DO NOTHING',(role,subject))
            assert connection.execute('SELECT subject FROM sarsa_booking.studio_identities WHERE role=%s',(role,)).fetchone()[0]==subject
            grant=Grant(role,subject,email,'synthetic-refresh',scopes_for(role))
            connection.execute('INSERT INTO sarsa_booking.google_connections(role,subject,client_id,revision,encrypted_grant,connected_at) VALUES(%s,%s,%s,1,%s,clock_timestamp())',(role,subject,CLIENT,cipher.seal(grant)))
            intent=uuid4();identifier='synthetic-'+role+'-sheet';intents[role]=str(intent)
            connection.execute("INSERT INTO sarsa_booking.google_workbooks(role,intent,subject,client_id,spreadsheet_id,state,connection_revision) VALUES(%s,%s,%s,%s,%s,'ready',1)",(role,intent,subject,CLIENT,identifier))
            files[identifier]={'id':identifier,'mimeType':'application/vnd.google-apps.spreadsheet','trashed':False,
                'owners':[{'emailAddress':email}],'appProperties':{'project':'004-sarsa-jyotish-sansthan','role':role,'intent':str(intent)}}
        old=connection.execute("SELECT payload FROM sarsa_booking.delivery_jobs WHERE kind='booking_cancelled' AND recipient_role='calendar'").fetchone()[0]
    def event(body):
        return dict(body,organizer={'email':OWNERS['client']},etag='synthetic-etag',
            conferenceData={'createRequest':{'status':{'statusCode':'success'}},
                'conferenceSolution':{'key':{'type':'hangoutsMeet'}},
                'entryPoints':[{'entryPointType':'video','uri':'https://meet.google.com/abc-defg-hij'}]})
    from backend.booking_engine.google_workspace import Workspace
    access=Access('synthetic-client',datetime.now(timezone.utc)+timedelta(hours=1),Grant('client','synthetic-completion-client',OWNERS['client'],'synthetic-refresh',scopes_for('client')))
    events[event_id(old['id'],old['revision'])]=event(Workspace(access).calendar_body(old))
    def google_request(request):
        url=str(request.url).split('?',1)[0]
        if url.startswith(CALENDAR):
            identifier=url.rsplit('/',1)[-1]
            if request.method=='GET':return httpx.Response(200,json=events[identifier]) if identifier in events else httpx.Response(404)
            mutations.append(request.method)
            if request.method=='POST':
                body=json.loads(request.content);events[body['id']]=event(body)
                return httpx.Response(201,json=events[body['id']])
            if request.method=='DELETE':events.pop(identifier,None);return httpx.Response(204)
        if url.startswith(DRIVE+'/'):return httpx.Response(200,json=files[url.rsplit('/',1)[-1]])
        if url.startswith(SHEETS) and '/values/' in url:
            if request.method=='GET':return httpx.Response(200,json={'values':rows[url]} if url in rows else {})
            assert request.method=='PUT';mutations.append(request.method);rows[url]=json.loads(request.content)['values']
            return httpx.Response(200,json={})
        raise AssertionError('Unexpected synthetic provider request.')
    def email_request(request):
        assert request.url.host=='api.resend.com' and request.method=='POST'
        mail.append(json.loads(request.content));return httpx.Response(200,json={'id':str(uuid4())})
    google=httpx.MockTransport(google_request)
    for _ in range(10):
        result=run_google_delivery_once(store,services,transport=google)
        if result['processed']==0:break
        assert result['state']=='done',result
    sender=ResendSender('re_'+'s'*32,transport=httpx.MockTransport(email_request))
    for _ in range(6):
        result=run_email_delivery_once(store,sender)
        if result['processed']==0:break
        assert result=={'processed':1,'retry':False},result
    assert mutations.count('DELETE')==1 and mutations.count('POST')==1 and len(rows)==2
    assert all(values[0][9:11]==['corrected@example.com','+919876543211'] for values in rows.values())
    assert len(mail)==3 and sum(message['to']==['corrected@example.com'] for message in mail)==2
    with owner() as connection:
        assert connection.execute("SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE state='delivered'").fetchone()[0]==4
        assert connection.execute("SELECT count(*) FROM sarsa_booking.delivery_jobs WHERE state='accepted'").fetchone()[0]==3
        assert connection.execute('SELECT count(*) FROM sarsa_booking.sheet_rows').fetchone()[0]==2
    before=(len(mutations),len(mail))
    assert run_google_delivery_once(store,services,transport=google)=={'processed':0}
    assert run_email_delivery_once(store,sender)=={'processed':0}
    assert before==(len(mutations),len(mail))
    print('PASS: corrected meeting, old meeting removal, two separately owned record copies and three messages completed; idle repeats produced no duplicate requests. Provider responses were synthetic.')


if __name__=='__main__':
    import sys
    actions={'prepare':prepare,'verify':verify,'deliveries':deliveries}
    if len(sys.argv)!=2 or sys.argv[1] not in actions:raise SystemExit('Use prepare, verify or deliveries for the owned local fixture only.')
    actions[sys.argv[1]]()
