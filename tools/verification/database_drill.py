"""Owned local PostgreSQL proof: contention, permissions and application recovery.

The runner accepts no connection URL. It creates labelled disposable containers
bound only to loopback, generates ephemeral credentials, and never contacts a
provider. Restore targets are new containers, never an existing database.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
import importlib.util
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
import traceback
from uuid import uuid4
import psycopg
from psycopg import sql
from pglast import ast,parse_sql
from pglast.stream import RawStream
from fastapi.testclient import TestClient

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
sys.path.insert(0,str(ROOT/'tools/backup'))
from envelope import encrypt,decrypt
from postgres import IMAGE,restore_check
from backend.booking_engine.application import Settings,create_application
from backend.booking_engine.migrate import apply,migration_sources
from backend.booking_engine.models import BookingRequest
from backend.booking_engine.policy import IST,policy_version
from backend.booking_engine.security import new_secret
from backend.booking_engine.storage import Store
from backend.booking_engine.tests import database_checks,checkout_resume_database_check,email_database_check,recovery_plan_database_check

class LocalDatabase:
    def __init__(self,directory,tag):
        self.name='sarsa-004-reliability-'+tag+'-'+secrets.token_hex(6)
        self.ownership=secrets.token_hex(16);self.directory=directory;self.password=secrets.token_urlsafe(32);self.web_password=secrets.token_urlsafe(32)
    def command(self,args,**kwargs):
        return subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,check=True,**kwargs)
    def __enter__(self):
        environment={**os.environ,'POSTGRES_PASSWORD':self.password}
        try:
            self.command(['docker','run','-d','--name',self.name,'--label','sarsa.verification.owner='+self.ownership,
                '-p','127.0.0.1::5432','--mount','type=bind,src='+str(self.directory)+',dst=/sarsa-tls,readonly',
                '-e','POSTGRES_PASSWORD','-e','POSTGRES_DB=neondb',IMAGE,'sh','-c',
                'cp /sarsa-tls/server.crt /tmp/server.crt; cp /sarsa-tls/server.key /tmp/server.key; chmod 600 /tmp/server.key; chown postgres:postgres /tmp/server.*; exec docker-entrypoint.sh postgres -c ssl=on -c ssl_cert_file=/tmp/server.crt -c ssl_key_file=/tmp/server.key'],env=environment)
            raw=self.command(['docker','port',self.name,'5432/tcp']).stdout.decode().strip()
            if not raw.startswith('127.0.0.1:'):raise RuntimeError('local_bind_rejected')
            self.port=int(raw.split(':')[1]);self.dsn=psycopg.conninfo.make_conninfo(host='127.0.0.1',port=self.port,user='postgres',password=self.password,dbname='neondb',sslmode='require',connect_timeout=3)
            for _ in range(60):
                try:
                    with psycopg.connect(self.dsn,autocommit=True) as c:
                        c.execute(sql.SQL('CREATE ROLE neondb_owner LOGIN SUPERUSER PASSWORD {}').format(sql.Literal(self.password)))
                        c.execute('CREATE ROLE neon_superuser NOLOGIN');c.execute('ALTER DATABASE neondb OWNER TO neondb_owner');c.execute('ALTER SCHEMA public OWNER TO neondb_owner');c.execute('REVOKE CREATE ON DATABASE neondb FROM PUBLIC');c.execute('REVOKE CREATE ON SCHEMA public FROM PUBLIC')
                    self.dsn=psycopg.conninfo.make_conninfo(self.dsn,user='neondb_owner');return self
                except psycopg.OperationalError:time.sleep(.2)
            raise RuntimeError('local_database_not_ready')
        except BaseException:self.close();raise
    def close(self):
        result=subprocess.run(['docker','inspect','--format','{{index .Config.Labels "sarsa.verification.owner"}}',self.name],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=20)
        if result.returncode==0 and result.stdout.decode().strip()==self.ownership:
            subprocess.run(['docker','rm','-f','-v',self.name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30,check=True)
    def __exit__(self,*args):self.close()
    def owner(self):return psycopg.connect(self.dsn,autocommit=True)
    def store(self):return Store(psycopg.conninfo.make_conninfo(self.dsn,user='sarsa_booking_web',password=self.web_password),expected_host='127.0.0.1')
    def prepare_login(self):
        with self.owner() as c:c.execute(sql.SQL('ALTER ROLE sarsa_booking_web PASSWORD {}').format(sql.Literal(self.web_password)))

def sql_checks(db):
    folder=ROOT/'backend/booking_engine/tests'
    checks=[(p.name,p.read_text()) for p in sorted(folder.glob('*.sql')) if p.name not in ('google_delivery_assertions.sql','email_dispatch_assertions.sql')]
    checks += [('receipt-query',database_checks.receipt_query_check()),('payment-lease',database_checks.recovery_check()),
        ('google-delivery',database_checks.google_delivery_check()),('workbook-ownership',database_checks.google_workbooks_check()),
        ('email-events',database_checks.email_events_check()),('checkout-resume',checkout_resume_database_check.render()),
        ('email-dispatch',email_database_check.render()),('recovery-plan',recovery_plan_database_check.render())]
    for name,source in checks:
        with db.owner() as c:
            try:
                c.execute('BEGIN')
                if name=='website_permissions.sql':c.execute('SET LOCAL ROLE sarsa_booking_web')
                c.execute(source)
            except Exception:raise RuntimeError('database_assertion_failed:'+name) from None
            finally:c.execute('ROLLBACK')
    return len(checks)

def seed_booking(db):
    store=db.store();now=datetime.now(IST);day=now.date()+timedelta(days=2)
    if day.isoweekday()==7:day+=timedelta(days=1)
    start=datetime.combine(day,datetime.min.time(),IST)+timedelta(hours=10)
    with db.owner() as c:c.execute("UPDATE sarsa_booking.intake_settings SET public_open=true,merchant_id='SarsaSynthetic',payment_mode='live',credential_version='drill'")
    context,reference=uuid4(),uuid4();credential=new_secret();store.create_context(context,'d'*64)
    draft=BookingRequest(request_id=reference,full_name='Sarsa synthetic recovery drill',email='test@example.com',phone='+919876543210',service_id='kundli-prediction',quote_version=policy_version(),starts_at=start)
    expected={'merchant_id':'SarsaSynthetic','mode':'live','credential_version':'drill'}
    reservation=store.reserve(context,draft,credential,b'a'*32,expected);assert reservation['code']=='reserved'
    booking=reservation['booking_id'];assert store.start_order_creation(context,booking)
    intent={'merchant_id':'SarsaSynthetic','mode':'live','credential_version':'drill'}
    assert store.record_order_creation(context,booking,intent,'order_drill')=='ready'
    from backend.booking_engine.payment_evidence import PaymentEvidence
    # Synthetic captured evidence is confined to the owned disposable database.
    evidence=PaymentEvidence(entity='payment',id='pay_drill',order_id='order_drill',status='captured',amount=250000,currency='INR',amount_refunded=0,captured=True)
    assert store.observe_payment(context,booking,intent,evidence)=='confirmed'
    return reference,credential,booking


def burst_reservations(db,booking):
    """Forty independent visitors compete for one new time, with real SQL locks."""
    with db.owner() as connection:
        start=connection.execute('SELECT starts_at+interval \'1 hour\' FROM sarsa_booking.bookings WHERE id=%s',(booking,)).fetchone()[0]
    def reserve(index):
        store=db.store();context=uuid4();store.create_context(context,secrets.token_hex(32))
        draft=BookingRequest(request_id=uuid4(),full_name='Synthetic burst visitor',email=f'load{index}@example.com',
            phone='+919876543210',service_id='kundli-prediction',quote_version=policy_version(),starts_at=start)
        return store.reserve(context,draft,new_secret(),b'a'*32,{'merchant_id':'SarsaSynthetic','mode':'live','credential_version':'drill'})['code']
    with ThreadPoolExecutor(max_workers=8) as pool:outcomes=list(pool.map(reserve,range(40)))
    assert outcomes.count('reserved')==1
    assert all(value in ('reserved','time_unavailable') for value in outcomes)
    with db.owner() as connection:
        assert connection.execute('SELECT count(*) FROM sarsa_booking.slot_claims WHERE starts_at=%s AND released_at IS NULL',(start,)).fetchone()[0]==1
    return len(outcomes)

def main():
    with tempfile.TemporaryDirectory(prefix='sarsa-reliability-') as directory:
        folder=Path(directory);os.chmod(folder,0o700)
        subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(folder/'server.key'),'-out',str(folder/'server.crt'),'-subj','/CN=localhost','-days','1'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True,timeout=30)
        with LocalDatabase(folder,'source') as source:
            with source.owner() as c:apply(c)
            source.prepare_login();count=sql_checks(source)
            spec=importlib.util.spec_from_file_location('sarsa_local_contention',ROOT/'tools/booking-checks/concurrency.py');module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);module.prove(source.dsn)
            reference,credential,booking=seed_booking(source)
            burst=burst_reservations(source,booking)
            store=source.store()
            with ThreadPoolExecutor(max_workers=8) as pool:claims=list(pool.map(lambda _:store.claim_google_delivery(),range(8)))
            active=[claim for claim in claims if claim];assert len({claim['id'] for claim in active})==len(active),'duplicate_live_lease'
            # A crash leaves a lease. Expiring it permits one new worker, fences
            # the abandoned worker, and preserves the original booking/payment.
            old=active[0]
            with source.owner() as c:c.execute('UPDATE sarsa_booking.delivery_jobs SET lease_expires_at=clock_timestamp()-interval \'1 second\' WHERE id=%s',(old['id'],))
            replacement=store.claim_google_delivery();assert replacement['id']==old['id'] and replacement['lease_token']!=old['lease_token']
            assert store.finish_google_delivery(old,'failed',error='synthetic_provider_outage') is False
            assert store.finish_google_delivery(replacement,'failed',error='synthetic_provider_outage') is True
            key=secrets.token_bytes(32);archive=folder/'recovery.aesgcm'
            process=subprocess.Popen(['docker','exec',source.name,'pg_dump','-U','neondb_owner','-d','neondb','--format=custom','--schema=sarsa_booking','--no-owner','--no-privileges'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            with archive.open('xb') as target:encrypt(process.stdout,target,key,{'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':datetime.now(timezone.utc).date().isoformat()})
            assert process.wait(timeout=60)==0;process.stdout.close();process.stderr.close()
            restore_check(archive,key,require_current=True)
            # A separate clean target reconstitutes roles/ACL from the checked
            # source. Archived provider credentials are never supplied here.
            with LocalDatabase(folder,'restored') as restored:
                acl=[];roles=[]
                for _,migration,_ in migration_sources():
                    for statement in parse_sql(migration):
                        if isinstance(statement.stmt,ast.CreateRoleStmt):roles.append(RawStream()(statement.stmt))
                        elif isinstance(statement.stmt,(ast.GrantStmt,ast.GrantRoleStmt,ast.AlterRoleStmt,ast.AlterRoleSetStmt,ast.AlterDefaultPrivilegesStmt)):acl.append(RawStream()(statement.stmt))
                with restored.owner() as c:
                    c.execute('CREATE EXTENSION btree_gist')
                    for statement in roles:c.execute(statement)
                with archive.open('rb') as encrypted:decrypt(encrypted,key)
                process=subprocess.Popen(['docker','exec','-i',restored.name,'pg_restore','-U','neondb_owner','-d','neondb','--no-owner','--no-privileges','--single-transaction','--exit-on-error'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                with archive.open('rb') as encrypted:decrypt(encrypted,key,process.stdin)
                process.stdin.close();assert process.wait(timeout=60)==0;process.stderr.close()
                with restored.owner() as c:
                    for statement in acl:c.execute(statement)
                    c.execute('BEGIN');c.execute('SET LOCAL ROLE sarsa_booking_web');c.execute((ROOT/'backend/booking_engine/tests/website_permissions.sql').read_text());c.execute('ROLLBACK')
                restored.prepare_login();settings=Settings('https://sarsa-drill.invalid',b'a'*32,b'b'*32,b'c'*32)
                client=TestClient(create_application(restored.store(),settings,verified_client_address=lambda r:'127.0.0.1'))
                headers={'Origin':settings.origin,'X-Booking-Receipt':credential}
                valid=client.post('/api/checkout/status',json={'request_id':str(reference)},headers=headers)
                assert valid.status_code==200 and valid.json()['appointment_state']=='confirmed'
                invalid=client.post('/api/checkout/status',json={'request_id':str(reference)},headers={**headers,'X-Booking-Receipt':new_secret()});assert invalid.status_code==403
                assert restored.store().recovery_plan()['lanes']['google'] is not None
                with restored.owner() as c:
                    assert c.execute('SELECT count(*) FROM sarsa_booking.accepted_payments WHERE booking_id=%s',(booking,)).fetchone()[0]==1
                    assert c.execute('SELECT count(*) FROM sarsa_booking.slot_claims WHERE booking_id=%s AND released_at IS NULL',(booking,)).fetchone()[0]==1
            evidence={'sql_groups':count,'migrations':len(migration_sources()),'independent_contention':True,'burst_visitors':burst,'burst_winners':1,'concurrent_worker_leases':len(active),
                'expired_lease_fenced':True,'archive_authenticated':True,'restored_application_receipt':True,'wrong_receipt_rejected':True,
                'restored_permissions_verified':True,'payment_and_slot_preserved':True,'providers_contacted':False}
            output=ROOT/'tools/verification/artifacts/database-drill.json';output.parent.mkdir(exist_ok=True,parents=True);output.write_text(json.dumps(evidence,indent=2)+'\n')
            print('PASS: isolated SQL, contention, crash recovery, encrypted restore and restricted application access.',flush=True)

if __name__=='__main__':
    try:main()
    except Exception as error:
        location=traceback.extract_tb(error.__traceback__)[-1]
        print('Drill diagnostic:',type(error).__name__,Path(location.filename).name,location.lineno)
        raise SystemExit('Isolated reliability drill failed. No credentials or private SQL values were logged; inspect the named assertion locally.') from None
