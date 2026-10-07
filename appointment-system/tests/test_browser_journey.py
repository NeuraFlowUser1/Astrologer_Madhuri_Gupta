"""Real common browser coordinator -> HTTP -> native SQL, with synthetic providers."""
import hashlib,hmac,json,os,shutil,subprocess,time,unittest
from datetime import datetime
from pathlib import Path
from .child_stream import ChildLines
from unittest.mock import Mock
from zoneinfo import ZoneInfo
from fastapi.testclient import TestClient
from appointment_system.application import create_application
from appointment_system.configuration import installation
from appointment_system.razorpay import Credentials,order_receipt
from appointment_system.recovery import Accounts
from .fixtures import business
from .test_sql_booking_verification import BookingCodeFixture


class BrowserJourneySQL(BookingCodeFixture):
    def journey(self,otp,*,website=False,no_email=False):
        spec=business(booking_otp=otp)
        if website:
            spec=json.loads((Path(os.environ['BOOKING_WEBSITE_PROOF_PROJECT'])/'appointment-settings/business-settings.json').read_text())
            otp=spec['booking_verification']['email']
        if no_email:
            otp=False;spec['booking_verification']['email']=False;spec['required_contacts']=['phone']
        self.set_policy(spec);adapter=Mock()
        adapter.credentials=Credentials('SyntheticMerchant','live','fixture','rzp_live_synthetic','synthetic-secret')
        captured=False;order={}
        def create(identifier,amount,**kwargs):
            nonlocal order
            order={'id':'order_synthetic','entity':'order','amount':amount,'currency':'INR',
                   'receipt':order_receipt(identifier,'live'),'partial_payment':False,'status':'created','amount_paid':0,'amount_due':amount}
            return dict(order)
        def payments(_):
            items=[{'id':'pay_synthetic','entity':'payment','order_id':order['id'],'amount':order['amount'],
                    'currency':'INR','status':'captured','captured':True,'amount_refunded':0}] if captured else []
            return {'entity':'collection','count':len(items),'items':items}
        adapter.create_order.side_effect=create;adapter.order.side_effect=lambda _:dict(order);adapter.order_payments.side_effect=payments
        adapter.payment.side_effect=lambda _:payments(None)['items'][0]
        accounts=Accounts([adapter],current_versions={('SyntheticMerchant','live'):'fixture'})
        app=create_application(self.public,self.settings,verified_client_address=lambda request:'127.0.0.1',
            projection_reader=self.reader,worker_store=self.worker,email_sender=self.sender,booking_verification_keys=self.keys,payment_accounts=accounts)
        self.client=TestClient(app,base_url=installation()['origin'])
        node=os.environ.get('BOOKING_NODE_EXECUTABLE') or shutil.which('node')
        self.assertIsNotNone(node,'Node is required for native browser coordinator proof')
        script='booking-website-native.mjs' if website else 'booking-browser-native.mjs'
        process=subprocess.Popen([node,str(Path(__file__).with_name(script))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        lines=ChildLines(process.stdout);completed=False
        try:
            deadline=time.monotonic()+90
            while time.monotonic()<deadline:
                line=lines.readline(timeout=1)
                if line is None:
                    if process.poll() is not None:break
                    continue
                if not line:break
                self.assertLess(len(line),16384);row=json.loads(line);path=row['path'];body={};status=200
                if path=='test:settings':body={key:installation()[key] for key in ('installation_id','environment')}|{'no_email':no_email}
                elif path=='test:date':body={'value':datetime.fromisoformat(self.starts[0]).astimezone(ZoneInfo('Asia/Kolkata')).date().isoformat()}
                elif path=='test:verification-code':body={'value':self.code()}
                elif path=='test:payment-capture':
                    self.assertEqual(row['order'],order['id']);captured=True
                    body={'razorpay_order_id':order['id'],'razorpay_payment_id':'pay_synthetic',
                        'razorpay_signature':hmac.new(b'synthetic-secret',(order['id']+'|pay_synthetic').encode(),hashlib.sha256).hexdigest()}
                elif path=='test:finished':completed=True
                else:
                    self.assertTrue(path.startswith('/api/'));headers=dict(self.headers)
                    if row.get('credential'):headers['X-Booking-Receipt']=row['credential']['secret']
                    response=self.client.post(path,headers=headers,json=row['body']) if 'body' in row else self.client.get(path,headers=headers)
                    status=response.status_code;body=response.json()
                process.stdin.write(json.dumps({'id':row['id'],'status':status,'body':body})+'\n');process.stdin.flush()
                if completed:break
            if not completed and process.poll() is None:process.kill()
            _,error=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,error[-2000:]);self.assertTrue(completed,'Coordinator did not complete its journey')
        finally:
            lines.close()
            if process.poll() is None:process.kill();process.wait()
            for stream in (process.stdin,process.stdout,process.stderr):stream.close()
            self.client.close()
        self.assertEqual(adapter.create_order.call_count,1)
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.accepted_payments;'),'1')
        self.assertEqual(len(self.requests),1 if otp else 0)
        if no_email:
            self.assertEqual(self.db.scalar('SELECT email IS NULL FROM appointment_system.bookings;'),'t')
            self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE recipient_role='customer';"),'0')
            self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.delivery_jobs WHERE kind='sheet_booking';"),'2')

    def test_without_booking_email_code(self):self.journey(False)
    def test_with_booking_email_code(self):self.journey(True)
    def test_without_booking_email(self):self.journey(False,no_email=True)

    @unittest.skipUnless(os.environ.get('BOOKING_WEBSITE_PROOF_PROJECT'),'Explicit built project required')
    def test_real_built_website(self):self.journey(False,website=True)

    @unittest.skipUnless(os.environ.get('BOOKING_WEBSITE_PROOF_PROJECT'),'Explicit built project required')
    def test_real_built_website_without_email(self):self.journey(False,website=True,no_email=True)
