"""Real protected parsers and bounded command failures; no provider or live database."""
import io,json,tempfile,unittest
from contextlib import redirect_stdout,redirect_stderr
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch
from appointment_system.configuration import profile
from appointment_system.serialization import canonical
from tools.conversion.operator_settings import selections,bindings
from tools.conversion.source import ConversionError,catalogue
from tools.conversion.records import Mapper
from tools.handover import main,run
from tools.conversion.difference import compare
from .handover_configuration import protected,selection
from . import test_conversion_grants as grant_fixture
from . import test_conversion_mail as mail_fixture
from .test_conversion_mail import job,message


class HandoverCommands(unittest.TestCase):
    def test_published_astro_source_needs_no_nonexistent_old_context_key(self):
        selected,env=protected('003')
        selected['receipt_formats'].pop('context-003',None)
        retained=json.loads(env['BOOKING_LEGACY_PROTECTION'])
        retained['readers']['context']={}
        retained['readers']['recovery']={}
        retained['materials']={}
        env['BOOKING_LEGACY_PROTECTION']=json.dumps(retained)
        selected=selections(canonical(selected),profile())
        bound=bindings(profile(),selected,env)
        self.assertEqual(dict(bound.receipt_formats),{
            'receipt-003':'retained-receipt','enquiry-003':'retained-enquiry'})
        invented=deepcopy(selected);invented['receipt_formats']['context-003']='nonexistent-old-context'
        with self.assertRaisesRegex(ConversionError,'conversion_selection_readers_invalid'):
            selections(canonical(invented),profile())
        with self.assertRaisesRegex(ConversionError,'conversion_selection_readers_invalid'):
            bindings(profile(),invented,env)
        # Sarsa really has existing context credentials and still requires them.
        sarsa,_=protected('004');sarsa['receipt_formats'].pop('context-004')
        with self.assertRaisesRegex(ConversionError,'conversion_selection_readers_invalid'):
            selections(canonical(sarsa),profile())

    def test_diff_rejects_other_installations_and_malformed_history_without_echoing_it(self):
        baseline=dict(phase='preview',installation_id='installation',environment='test',layout='legacy-003-16',
                      release_digest='a'*64,structure_digest='b'*64,source_counts={'public.bookings':1},
                      source_table_digests={'public.bookings':'c'*64})
        self.assertFalse(compare(baseline,baseline)['source_changed'])
        current=baseline|{'source_counts':{'public.bookings':2},'source_table_digests':{'public.bookings':'d'*64}}
        self.assertEqual(compare(baseline,current)['source_changes'],[dict(table='public.bookings',previous_count=1,current_count=2,contents_changed=True)])
        for change in ({'installation_id':'other'},{'release_digest':'e'*64},{'phase':'complete'},
                       {'source_counts':{}},{'source_counts':{'public.bookings':True}},
                       {'source_table_digests':{'public.bookings':'private contents'}}):
            with self.subTest(fields=list(change)),self.assertRaises(ConversionError) as error:
                compare(baseline|change,current)
            self.assertNotIn('private contents',str(error.exception))

    def test_both_source_profiles_build_real_retained_readers_without_provider_calls(self):
        for project in ('003','004'):
            with self.subTest(project=project):
                selected,env=protected(project,integrations=True)
                selected=selections(canonical(selected),profile());bound=bindings(profile(),selected,env)
                self.assertEqual(bound.payment(key_id='rzp_test_legacy')['merchant_id'],'merchant123')
                self.assertIsNotNone(bound.history_mapper.recovery)
                proof=grant_fixture.HistoricalGoogleGrants();proof.setUp()
                layout=next(item for item in catalogue() if item.identifier==selected['source_layout'])
                if project=='004':
                    result=bound.resource_mapper(layout,'google_connections',[proof.full()],{})
                    self.assertEqual(result['google_resource_grants'][0]['owner_email'],'practice@example.test')
                    enquiry=job();enquiry.update(kind='acknowledgement',request_id='aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa')
                    enquiry.pop('booking_id');enquiry=mail_fixture.LegacyMailTransfer().encrypted(enquiry,message(enquiry,project))
                    mail=bound.mail_mapper(layout,'enquiry_delivery_jobs',enquiry)
                    self.assertEqual(mail['mail_credential_version'],'k1')
                else:
                    result=bound.resource_mapper(layout,'google_connection',[proof.calendar(bare=True)],{})
                    self.assertEqual(result['google_resource_grants'][0]['last_error_code'],'legacy_owner_verification_required')
                self.assertNotIn('synthetic-secret',repr(bound))

    def test_missing_selected_reader_and_foreign_protected_account_fail_before_use(self):
        selected,env=protected('004',integrations=True)
        for changes in ({'BOOKING_LEGACY_PROTECTION':'{}'}, {'BOOKING_GOOGLE_RESOURCES':'{}'},
                        {'BOOKING_RAZORPAY_ACCOUNTS':'{}'}, {'BOOKING_LEGACY_GOOGLE_GRANTS':'{}'}):
            with self.subTest(setting=list(changes)),self.assertRaises((ValueError,KeyError,ConversionError)):
                bindings(profile(),selected,env|changes)
        selected['receipt_formats']['receipt-004']='missing'
        with self.assertRaisesRegex(ConversionError,'conversion_reader_not_prepared'):
            bindings(profile(),selected,env)
        selected,env=protected('004',integrations=True)
        selected['google']['full_grant_reader']='missing'
        with self.assertRaisesRegex(ConversionError,'conversion_resource_reader_invalid'):
            bindings(profile(),selected,env)

    def test_selection_rejects_foreign_target_unknown_fields_ambiguous_types_and_unproved_layout(self):
        original=selection('004')
        cases=[{'installation_id':'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'},{'environment':'production'},
               {'source_layout':'legacy-004-52'},{'writer_roles':[]},{'writer_roles':['sarsa_booking_web']*2},
               {'writer_roles':['owner; DROP TABLE bookings']},{'writer_roles':[None]},
               {'receipt_formats':{}},{'receipt_formats':{'receipt-004':True,'context-004':'a','enquiry-004':'b'}},
               {'recovery_reader':True},{'mail':{'credential_version':'k1','contact_message_formats':['one']}},
               {'google':{'calendar_client':3,'resource_formats':{},'full_grant_reader':None}},
               {'unexpected':'rejected'},{'version':True}]
        for change in cases:
            with self.subTest(fields=list(change)),self.assertRaises((ValueError,ConversionError)):
                selections(canonical(original|change),profile())
        raw=canonical(original).decode()
        with self.assertRaises(ValueError):selections(raw[:-1]+',"version":1}',profile())

    def test_invalid_command_shape_is_rejected_before_reading_secrets_or_connecting(self):
        for action,identifier,digest in [('unknown',None,None),('preview','id',None),('prepare','id',None),
                                         ('convert',None,None),('complete','id',None),('checkpoint',None,'a'*64)]:
            with self.subTest(action=action),self.assertRaises(ConversionError):
                run(action,None,profile(),'a'*64,selection('004'),{},identifier=identifier,expected_digest=digest)

    def test_terminal_failures_do_not_print_raw_provider_credentials_or_database_errors(self):
        with tempfile.TemporaryDirectory(prefix='abs-handover-command-') as directory:
            root=Path(directory);spec=root/'selection.json';spec.write_bytes(canonical(selection('004')))
            for failure in (ValueError('postgresql://private-password@private-host/customer'),KeyboardInterrupt()):
                output=io.StringIO();error=io.StringIO()
                with patch('appointment_system.runtime.contained_release',return_value=(root,'a'*64)),\
                     patch('appointment_system.configuration.load',return_value=profile()),\
                     patch('tools.handover.migration_connection',side_effect=failure),\
                     redirect_stdout(output),redirect_stderr(error):
                    result=main(['checkpoint','--specification',str(spec)],environment={})
                self.assertEqual(result,1);self.assertEqual(output.getvalue(),'')
                self.assertNotIn('private-password',error.getvalue());self.assertNotIn('private-host',error.getvalue())
                self.assertIn('checkpoint',error.getvalue().lower())
