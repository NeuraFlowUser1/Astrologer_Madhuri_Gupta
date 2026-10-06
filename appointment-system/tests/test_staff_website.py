"""Actual shared staff HTML/scripts with native SQL and synthetic provider login."""
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time
import unittest
from appointment_system.configuration import installation
from .test_sql_staff_enquiries import StaffEnquiriesSQL
from .test_sql_staff import StaffFixture

class StaffWebsite(StaffEnquiriesSQL):
    @unittest.skipUnless(os.environ.get('BOOKING_CHROME_EXECUTABLE'),'Explicit local Chrome required')
    def test_shared_staff_changes_and_enquiry_review_survive_lost_replies_and_off(self):
        booking_fixture=StaffFixture();booking_fixture.db=self.db;booking_fixture.setUp()
        booking=booking_fixture.confirmed();self.reader.enabled=True
        self.sign_in('booking')
        self.start();code,_=self.code();self.assertEqual(self.verify(code).status_code,200)
        self.headers.pop('x-enquiry-receipt',None)
        process=subprocess.Popen([shutil.which('node'),str(Path(__file__).with_name('staff-website-native.mjs'))],
            stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,bufsize=1)
        selector=selectors.DefaultSelector();selector.register(process.stdout,selectors.EVENT_READ);completed=False
        try:
            deadline=time.monotonic()+160;buffer=b'';messages=[]
            while time.monotonic()<deadline:
                if not messages:
                    if not selector.select(timeout=1):
                        if process.poll() is not None:break
                        continue
                    part=os.read(process.stdout.fileno(),65536)
                    if not part:break
                    buffer+=part;self.assertLess(len(buffer),131072)
                    chunks=buffer.split(b'\n');buffer=chunks.pop();messages.extend(chunks)
                    if not messages:continue
                line=messages.pop(0)
                self.assertLess(len(line),16384);row=json.loads(line);path=row['path']
                if path=='test:settings':value={'status':200,'body':json.dumps({'reference':booking['request'],'starts_at':booking_fixture.starts[0],'next_start':booking_fixture.starts[2]})}
                elif path=='test:off':
                    self.reader.enabled=False;self.db.sql('UPDATE appointment_system.control_product_state SET enabled=false,requested_enabled=false;')
                    value={'status':200,'body':'{}'}
                elif path=='test:finished':completed=True;value={'status':200,'body':'{}'}
                else:
                    self.assertTrue(path in ('/studio','/enquiries-studio','/api/service-state') or path.startswith(('/api/studio/','/api/enquiry-studio/')))
                    headers={'Origin':installation()['origin']}
                    response=self.client.post(path,json=row['body'],headers=headers) if 'body' in row else self.client.get(path,headers=headers)
                    value={'status':response.status_code,'body':response.text,'contentType':response.headers.get('content-type','application/json')}
                try:process.stdin.write(json.dumps({'id':row['id'],**value})+'\n');process.stdin.flush()
                except BrokenPipeError:break
                if completed:break
            if not completed and process.poll() is None:process.kill()
            _,error=process.communicate(timeout=10);self.assertEqual(process.returncode,0,error[-3000:]);self.assertTrue(completed)
        finally:
            selector.close()
            if process.poll() is None:process.kill();process.wait()
            for stream in (process.stdin,process.stdout,process.stderr):stream.close()
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.staff_appointment_actions WHERE action='reschedule';"),'1')
        self.assertEqual(self.db.scalar("SELECT count(*) FROM appointment_system.staff_reviews WHERE note='Synthetic saved enquiry review';"),'1')
