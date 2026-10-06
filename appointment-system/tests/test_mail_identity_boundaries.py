"""Mail ownership stays explicit across retained readers and webhook rotation."""
import base64,json,unittest
from copy import deepcopy
from uuid import uuid4
from appointment_system.configuration import installation
from appointment_system.email_configuration import connection,webhook
from appointment_system.email_events import EmailWebhook
from appointment_system.mail_identity import MailIdentity,retained_key,tags_for
from .test_mail_contracts import document


class MailIdentityBoundaries(unittest.TestCase):
    def test_identity_rejects_unknown_format_invalid_address_and_sender_mismatch(self):
        value=document()['legacy_identities'][0]
        for changes in ({'format':'unknown'},{'project':'with spaces'},{'sender':'wrong@example.com'},
            {'reply_to':''},{'event_account_id':'bad\naccount'},{'address':'not-an-address'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):MailIdentity(**(value|changes))
        identity=MailIdentity(**value);job=str(uuid4())
        self.assertIsNone(identity.binding([] ,event=True));self.assertIsNone(identity.binding({'project':identity.project,'job_id':'not-a-uuid'},event=True))
        self.assertTrue(identity.owns_event({'project':identity.project}));self.assertFalse(identity.owns_event({'project':'foreign'}))
        self.assertIsNone(identity.binding({'project':identity.project,'job_id':job,'extra':'unapproved'},event=True))
        with self.assertRaises(ValueError):retained_key('booking/'+job+'/kind/client/v1',job,identity,booking_id=job,kind='invalid kind',role='client')

    def test_untagged_historical_reader_does_not_claim_unknown_tagged_events(self):
        value=document()['legacy_identities'][0]|{'format':'resend-legacy-untagged-job-v1'};identity=MailIdentity(**value)
        self.assertIsNone(identity.binding([]));self.assertFalse(identity.owns_event({}));self.assertTrue(identity.accepts({'from':identity.sender},str(uuid4())))
        self.assertFalse(identity.accepts({'from':identity.sender,'tags':[]},str(uuid4())))
        current=MailIdentity.current();tags={v['name']:v['value'] for v in tags_for(str(uuid4()))}
        self.assertTrue(current.owns_event(tags));self.assertFalse(current.owns_event(tags|{'installation':str(uuid4())}))

    def test_duplicate_or_current_identity_cannot_be_declared_as_a_retained_reader(self):
        for identities in ([document()['legacy_identities'][0]]*2,[document()['legacy_identities'][0]|{'format':'resend-v1'}]):
            with self.assertRaises(ValueError):connection(json.dumps(document()|{'legacy_identities':identities}))

    def test_notification_key_rotation_requires_unique_ids_secrets_and_owned_identity(self):
        declared=connection(json.dumps(document()));secret='whsec_'+base64.b64encode(b's'*32).decode()
        facts=installation();base={'version':1,'installation_id':facts['installation_id'],'environment':facts['environment'],'provider':'resend','purpose':'email-webhook'}
        for keys in ([],[{'key_id':'a','secret':secret}]*3,[{'key_id':'a','secret':secret},{'key_id':'b','secret':secret}],
            [{'key_id':'a','secret':secret},{'key_id':'a','secret':'whsec_'+base64.b64encode(b't'*32).decode()}],
            [{'key_id':'with spaces','secret':secret}]):
            with self.subTest(size=len(keys)),self.assertRaises(ValueError):webhook(json.dumps(base|{'key_map':{declared.account_id:{'keys':keys}}}),declared)
        for identities in ((),[],(object(),),(declared.identities[0],declared.identities[0])):
            with self.assertRaises(ValueError):EmailWebhook((secret,),identities=identities)
