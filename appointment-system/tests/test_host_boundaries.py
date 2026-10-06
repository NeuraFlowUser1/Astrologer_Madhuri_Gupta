"""Wrong hosts, obsolete routes and missing duties cannot cross website boundaries."""
import asyncio
from unittest import TestCase
from unittest.mock import Mock,patch
from starlette.requests import Request
from fastapi.testclient import TestClient
from appointment_system import hosting,surfaces
from appointment_system.visibility import BookingVisibility
from appointment_system.retired_routes import RetiredSubmissions,RETIRED_PATHS
from appointment_system.connection import StorageUnavailable
from appointment_system.storage import UnavailableStore
from appointment_system.configuration import installation
from appointment_system.serialization import canonical
from .test_application import environment,protection

class HostBoundaries(TestCase):
    def test_only_a_single_valid_platform_address_is_used(self):
        for raw,expected in [([(b'x-vercel-forwarded-for',b'192.0.2.9')],'192.0.2.9'),
            ([(b'x-vercel-forwarded-for',b'2001:db8::1')],'2001:db8::1'),([],None),
            ([(b'x-forwarded-for',b'192.0.2.9')],None),([(b'x-vercel-forwarded-for',b'fe80::1%eth0')],None),
            ([(b'x-vercel-forwarded-for',b'192.0.2.9, 192.0.2.10')],None),
            ([(b'x-vercel-forwarded-for',b'192.0.2.9')]*2,None)]:
            self.assertEqual(hosting.vercel_client_address(Request({'type':'http','headers':raw})),expected)

    def test_missing_duties_never_reuse_the_web_connection(self):
        with self.assertRaises(StorageUnavailable):hosting.purpose_store({},'web')
        for purpose in ('staff','worker','company'):
            self.assertIsInstance(hosting.purpose_store({'BOOKING_DATABASE_URL':'other-duty'},purpose),UnavailableStore)
        for purpose,key in [('web','BOOKING_DATABASE_URL'),('staff','BOOKING_STAFF_DATABASE_URL')]:
            with patch.object(hosting,'Store',return_value='synthetic-store') as factory:
                self.assertEqual(hosting.purpose_store({key:'synthetic-purpose-url'},purpose),'synthetic-store')
                factory.assert_called_once_with('synthetic-purpose-url',expected_host=installation()['database_targets'][purpose]['host'],purpose=purpose)

    def test_journal_is_separate_when_declared_and_unknown_credentials_cannot_fall_back(self):
        facts=installation();web=object()
        with patch.object(hosting,'installation',return_value=facts|{'database_targets':{key:value for key,value in facts['database_targets'].items() if key!='journal'}}):
            self.assertIs(hosting.ingress_store({},web),web)
        declared=facts|{'database_targets':facts['database_targets']|{'journal':{'host':'journal.example.test'}}}
        with patch.object(hosting,'installation',return_value=declared):
            self.assertIsInstance(hosting.ingress_store({},web),UnavailableStore)
            with patch('appointment_system.provider_ingress.JournalStore',return_value='synthetic-journal') as factory:
                result=hosting.ingress_store({'BOOKING_JOURNAL_KEYS':canonical(protection('provider-journal',34)),
                    'BOOKING_JOURNAL_DATABASE_URL':'synthetic-journal-url'},web)
                self.assertEqual(result,'synthetic-journal');self.assertEqual(factory.call_args.kwargs['expected_host'],'journal.example.test')

    def test_preview_or_foreign_environment_cannot_start_the_production_application(self):
        for change in ({},{'VERCEL':'1','VERCEL_ENV':'preview'},{'VERCEL':'0','VERCEL_ENV':'production'}):
            client=TestClient(hosting.create_hosted_application(environment()|change,release_digest='a'*64),base_url=installation()['origin'])
            response=client.get('/api/health');self.assertEqual(response.status_code,503)
            self.assertNotIn('DATABASE',response.text);self.assertIn('no-store',response.headers['cache-control'])

    def test_route_classification_rejects_ambiguous_addresses_and_uses_longest_owned_surface(self):
        for path in (None,123,'relative','/a%2fb','/a\\b','/a?b','/a#b','/a/../b','/a\x00b'):
            with self.subTest(path=path):self.assertEqual(surfaces.classify(path),'invalid')
        declared=installation()|{'surfaces':[{'path':'/','class':'general'},{'path':'/services','class':'mixed'},
            {'path':'/services/online','class':'booking'},{'path':'/portrait','class':'booking'}]}
        with patch.object(surfaces,'installation',return_value=declared):
            self.assertEqual(surfaces.classify('/services/online/photo'),'booking')
            self.assertEqual(surfaces.classify('/services/offline/details'),'mixed')
            self.assertEqual(surfaces.classify('/portrait.html'),'booking')
            self.assertEqual(surfaces.classify('/index.html'),'general')
            self.assertEqual(surfaces.classify('/BOOKING//index.html'),'booking')
            self.assertEqual(surfaces.classify('/api/company/support'),'private')
            self.assertEqual(surfaces.classify('/unrelated'),'general')

    def test_invalid_and_retired_paths_never_parse_a_body_or_enter_application(self):
        async def proof():
            async def refused(*args):raise AssertionError('Protected request reached application or input parser')
            for guard,path,status in [(BookingVisibility(refused,None),'/a%2fb',400),
                *((RetiredSubmissions(refused),path+'/',410) for path in RETIRED_PATHS)]:
                messages=[]
                async def send(message):messages.append(message)
                await guard({'type':'http','path':path,'method':'POST','headers':[]},refused,send)
                self.assertEqual(messages[0]['status'],status)
                self.assertTrue(any(name==b'cache-control' and b'no-store' in value for name,value in messages[0]['headers']))
            calls=[]
            async def downstream(*args):calls.append(args)
            scope={'type':'lifespan'}
            for guard in (hosting.CanonicalHost(downstream),BookingVisibility(downstream,None),RetiredSubmissions(downstream)):
                await guard(scope,refused,refused)
            self.assertEqual(len(calls),3);self.assertTrue(all(call[0] is scope for call in calls))
        asyncio.run(proof())
