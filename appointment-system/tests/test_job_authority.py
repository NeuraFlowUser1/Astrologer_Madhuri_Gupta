"""Job ownership includes an exact attempt, release and restored installation."""
from dataclasses import replace
from uuid import uuid4
import unittest
from appointment_system.job_authority import JobClaim
from .fixtures import installation

class JobAuthorityTests(unittest.TestCase):
    def setUp(self):
        self.claim=JobClaim('booking',str(uuid4()),str(uuid4()),1,installation()['installation_id'],str(uuid4()),'a'*64,1)

    def test_saved_claim_preserves_all_authority_fields(self):
        value=dict(zip(('id','lease_token','attempts','claim_installation','claim_generation','claim_release','claim_contract'),self.claim.parameters()[1:]))
        self.assertEqual(JobClaim.saved('booking',value),self.claim)
        self.assertEqual(self.claim.parameters()[0],'booking')
        for kind in ('contact','booking_code'):self.assertEqual(replace(self.claim,kind=kind).parameters()[0],kind)

    def test_invalid_attempt_release_contract_identity_or_kind_is_rejected(self):
        changes=[('kind',None),('kind','foreign'),('attempt',True),('attempt',0),('attempt',2147483648),
                 ('writer_contract',True),('writer_contract',2),('release_digest',None),('release_digest','A'*64),
                 ('installation_id',str(uuid4()))]
        for field in ('identifier','lease','installation_id','generation'):
            changes.extend((field,value) for value in (None,True,42,'BAD','00000000-0000-0000-0000-000000000000'))
        for field,value in changes:
            with self.subTest(field=field,value=value),self.assertRaisesRegex(ValueError,'job_claim_invalid'):replace(self.claim,**{field:value})
        for value in (None,{},[],True):
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'job_claim_invalid'):JobClaim.saved('booking',value)
