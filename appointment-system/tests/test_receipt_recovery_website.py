"""Built customer recovery pages use the canonical API and native purpose-limited SQL."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
import unittest
from .test_sql_receipt_recovery import ReceiptRecoveryFixture
from appointment_system.configuration import installation


@unittest.skipUnless(os.environ.get('BOOKING_WEBSITE_PROOF_PROJECT'),'Explicit built project required')
class ReceiptRecoveryWebsite(ReceiptRecoveryFixture):
    def test_built_page_recovers_after_lost_reply_and_off_hides_recovery(self):
        booking=self.confirmed();_,code,_=self.issue(booking)
        node=shutil.which('node');self.assertIsNotNone(node)
        process=subprocess.Popen([node,str(Path(__file__).with_name('receipt-recovery-website.mjs'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ);completed=False
        try:
            deadline=time.monotonic()+100
            while time.monotonic()<deadline:
                if not selector.select(timeout=1):
                    if process.poll() is not None:break
                    continue
                line=process.stdout.readline()
                if not line:break
                self.assertLess(len(line),16384);row=json.loads(line);path=row['path'];status=200;body={}
                if path=='test:settings':body={'reference':booking['request'],'code':code}
                elif path=='test:finished':completed=True
                else:
                    self.assertIn(path,('/api/booking-policy','/api/checkout/status','/api/checkout/recover-receipt'))
                    headers={'Origin':installation()['origin'],**row.get('headers',{})}
                    response=self.client.post(path,headers=headers,json=row['body']) if 'body' in row else self.client.get(path,headers=headers)
                    body=response.json();status=response.status_code
                process.stdin.write(json.dumps({'id':row['id'],'status':status,'body':body})+'\n');process.stdin.flush()
                if completed:break
            if not completed and process.poll() is None:process.kill()
            _,error=process.communicate(timeout=10)
            self.assertEqual(process.returncode,0,error[-2000:]);self.assertTrue(completed)
        finally:
            selector.close()
            if process.poll() is None:process.kill();process.wait()
            for stream in (process.stdin,process.stdout,process.stderr):stream.close()
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.receipt_recoveries WHERE redeemed_at IS NOT NULL;'),'1')
        self.assertEqual(self.db.scalar('SELECT count(*) FROM appointment_system.bookings;'),'1')
