"""Common enquiry browser -> real HTTP -> native SQL, with booking OFF throughout."""
import contextlib,json,os,selectors,shutil,subprocess,time,unittest
from pathlib import Path
from appointment_system.configuration import installation
from appointment_system.receipt_view import timestamp
from tools.checks.sql_target import literal
from .test_sql_enquiry_flow import EnquiryFixture


class EnquiryBrowserJourneySQL(EnquiryFixture):
    def journey(self,website=False):
        node=os.environ.get('BOOKING_NODE_EXECUTABLE') or shutil.which('node')
        self.assertIsNotNone(node)
        script='enquiry-website-native.mjs' if website else 'enquiry-browser-native.mjs'
        forms=['/contact']
        if website:
            profile=json.loads((Path(os.environ['BOOKING_WEBSITE_PROOF_PROJECT'])/'appointment-settings/enquiry-browser.json').read_text())
            if 'prashna' in profile['channels']:forms=['/contact','/','/services/prashna-kundali']
        process=subprocess.Popen([node,str(Path(__file__).with_name(script))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ);completed=False
        try:
            deadline=time.monotonic()+120
            while time.monotonic()<deadline:
                if not selector.select(timeout=1):
                    if process.poll() is not None:break
                    continue
                line=process.stdout.readline()
                if not line:break
                self.assertLess(len(line),16384);row=json.loads(line);path=row['path'];body={};status=200;response_headers={}
                if path=='test:settings':
                    body={key:installation()[key] for key in ('installation_id','environment')}
                    if website:body['forms']=forms
                elif path=='test:code':
                    ref=row['request_id']
                    saved=self.db.value('SELECT jsonb_build_object(\'email\',payload->>\'email\',\'generation\',generation,'
                        '\'ciphertext\',code_ciphertext,\'format\',code_format,\'expires\',code_expires_at) '
                        'FROM appointment_system.enquiries WHERE request_id='+literal(ref)+';')
                    body={'value':self.keys.open_code(saved['ciphertext'],ref,saved['email'],saved['generation'],timestamp(saved['expires']),format=saved['format'])}
                elif path=='test:finished':completed=True
                else:
                    self.assertTrue(path.startswith('/api/contact/'));headers={'Origin':installation()['origin'],**row.get('headers',{})}
                    response=self.client.post(path,headers=headers,json=row['body']) if 'body' in row else self.client.get(path,headers=headers)
                    status=response.status_code;body=response.json()
                    if response.headers.get('retry-after'):response_headers['retry-after']=response.headers['retry-after']
                try:
                    process.stdin.write(json.dumps({'id':row['id'],'status':status,'body':body,'headers':response_headers})+'\n');process.stdin.flush()
                except BrokenPipeError:break
                if completed:break
            if not completed and process.poll() is None:process.kill()
            _,error=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,error[-2000:]);self.assertTrue(completed)
        finally:
            selector.close()
            if process.poll() is None:process.kill();process.wait()
            for stream in (process.stdin,process.stdout,process.stderr):
                with contextlib.suppress(BrokenPipeError):stream.close()
            self.client.close()
        count=len(forms) if website else 2
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.enquiries WHERE verified_at IS NOT NULL;'),str(count))
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.enquiry_delivery_jobs WHERE kind<>'verification';"),str(count*4))
        self.assertEqual(self.db.scalar('SELECT enabled FROM appointment_system.control_product_state;'),'f')

    def test_contact_and_prashna_shared_browser_with_booking_off(self):self.journey()

    @unittest.skipUnless(os.environ.get('BOOKING_WEBSITE_PROOF_PROJECT'),'Explicit built project required')
    def test_real_built_website_with_booking_off(self):self.journey(website=True)
