"""Operator-only exact idempotent replay of this release's saved OFF command.

No new operation, customer action or worker recovery is created. Refuse any
changed owner intent; retain the original operation and report fresh evidence.
"""
import importlib.util
import json
from pathlib import Path
import time
import httpx

here=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('release_operator',here/'operator-004.py')
op=importlib.util.module_from_spec(spec);spec.loader.exec_module(op)
intent=json.loads((here/'company-off-intent.json').read_text())
body=intent['body']
assert body['enabled'] is False
private=op.module('existing_company_credentials',op.SHARED/'001-implementation-evidence/2026-10-07-booking-experience/company-credential-store.py')
with httpx.Client(base_url=op.ORIGIN,timeout=35,trust_env=False,follow_redirects=False) as client:
    csrf=None
    try:
        values=private.access('004')
        try:login=op.request(client,'POST','/api/company/sign-in/start',values)
        finally:values.clear()
        if login.get('signed_in') is not True:raise op.Stop('company_signin_not_confirmed')
        state=op.request(client,'GET','/api/company/control/status')
        snap,csrf,public=op.snapshot(state)
        if (public['operation_id']!=body['operation_id'] or snap['restore_generation']!=body['generation']
            or str(snap['revision'])!=str(int(body['revision'])+1) or snap['enabled'] is not False
            or public['requested_mode']!='off' or public['admission_mode']!='off'):
            raise op.Stop('owner_intent_changed_do_not_replay')
        reply=op.request(client,'POST','/api/company/control/change',body,csrf)
        receipt=reply.get('receipt',{})
        if receipt.get('operation_id')!=body['operation_id'] or receipt.get('requested_enabled') is not False:
            raise op.Stop('same_operation_receipt_mismatch')
        for attempt in range(15):
            state=op.request(client,'GET','/api/company/control/status')
            snap,csrf,public=op.snapshot(state)
            if public['operation_id']!=body['operation_id']:raise op.Stop('newer_owner_command_won')
            if public['requested_mode']=='off' and public['admission_mode']=='off' and snap['enabled'] is False and public['progress']=='effective':
                result={'successful':True,'observed_at':op.now(),'operation_id':body['operation_id'],'snapshot':public,'exact_saved_replay':True}
                op.save('company-off.json',result);op.save('company-off-retry.json',result)
                print(json.dumps(result));break
            time.sleep(2)
        else:raise op.Stop('same_operation_publication_pending')
    finally:
        if csrf:
            try:op.request(client,'POST','/api/company/sign-out',{},csrf)
            except Exception:pass
        client.cookies.clear()
