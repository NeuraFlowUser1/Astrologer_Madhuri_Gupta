"""Fail before cutover on ambiguous authority, ownership or import collisions."""
from contextlib import nullcontext
from dataclasses import replace
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from uuid import uuid4
import psycopg
from appointment_system.settings import Installation
from tools.conversion.handover import Handover,migration_connection
from tools.conversion.records import Translation
from tools.conversion.source import ConversionError
from .test_conversion_records import bindings


class HandoverFailureBoundaries(TestCase):
    def setUp(self):
        bound=bindings();facts=bound.installation.document
        facts['database_targets']['migration']=dict(facts['database_targets']['web'],role='synthetic_owner',pooling=False)
        self.bindings=replace(bound,installation=Installation.parse(facts),receipt_formats=dict(bound.receipt_formats));self.connection=Mock(autocommit=True)
        self.hand=Handover(self.connection,self.bindings,'a'*64,('old_writer',),expected_layout='legacy-003-16')

    def test_constructor_and_explicit_source_layout_are_not_guessed(self):
        for release,roles in [('invalid',('old_writer',)),('a'*64,()),('a'*64,['old_writer']),('a'*64,('old_writer','old_writer')),('a'*64,('owner;drop',))]:
            with self.assertRaises(ConversionError):Handover(self.connection,self.bindings,release,roles)
        with self.assertRaises(ConversionError):Handover(self.connection,self.bindings,'a'*64,('old_writer',),expected_layout='unknown')
        with patch('tools.conversion.handover.detect',return_value=SimpleNamespace(identifier='legacy-004-31')):
            with self.assertRaisesRegex(ConversionError,'layout_mismatch'):self.hand.layout()

    def test_connection_requires_configured_identity_and_preserves_tls_without_exposing_failure(self):
        with patch('tools.conversion.handover.configured_installation',return_value={}):
            with self.assertRaisesRegex(ConversionError,'identity_mismatch'):
                with migration_connection('synthetic-private-connection',self.bindings.installation):self.fail('Connected to foreign target')
        with patch('tools.conversion.handover.configured_installation',return_value=self.bindings.installation.document),\
             patch('tools.conversion.handover.checked_config',return_value={'host':'fixture.example.test'}),\
             patch('tools.conversion.handover.psycopg.connect',return_value=nullcontext(self.connection)) as connect:
            with migration_connection('synthetic-private-connection',self.bindings.installation) as result:self.assertIs(result,self.connection)
            self.assertEqual(connect.call_args.kwargs['sslmode'],'verify-full');self.assertEqual(connect.call_args.kwargs['channel_binding'],'require')
            connect.side_effect=psycopg.OperationalError('private-provider-detail')
            with self.assertRaisesRegex(ConversionError,'connection_unavailable') as raised:
                with migration_connection('synthetic-private-connection',self.bindings.installation):self.fail('Connected')
            self.assertNotIn('private-provider-detail',str(raised.exception))

    def test_nonidle_connection_owner_role_and_target_document_mismatch_refuse_work(self):
        self.connection.autocommit=False
        with self.assertRaisesRegex(ConversionError,'idle_connection_required'):
            with self.hand.transaction():self.fail('Entered transaction')
        self.connection.autocommit=True
        target=self.bindings.installation.document['database_targets']['migration']
        for owner,document,code in [(('wrong','wrong',True),None,'owner_required'),((target['database'],target['role'],True),None,'identity_mismatch'),
            ((target['database'],target['role'],True),({},),'identity_mismatch')]:
            self.connection.execute.side_effect=[Mock(fetchone=lambda:owner),Mock(fetchone=lambda:document)]
            with self.assertRaisesRegex(ConversionError,code):self.hand.owner()
        self.connection.execute.side_effect=None;self.connection.transaction.return_value=nullcontext()
        with patch.object(self.hand,'owner',side_effect=psycopg.errors.LockNotAvailable('private detail')):
            with self.assertRaisesRegex(ConversionError,'conversion_transaction_55P03') as raised:
                with self.hand.transaction():self.fail('Owner not ready')
            self.assertNotIn('private detail',str(raised.exception))

    def test_checkpoint_refuses_invalid_foreign_or_missing_saved_handover(self):
        for value in ('bad','00000000-0000-0000-0000-000000000000'):
            with self.assertRaisesRegex(ConversionError,'checkpoint_invalid'):self.hand.checkpoint(value)
        row=[str(uuid4()),'prepared','legacy-003-16','a'*64,['old_writer'],None,None,None,{},{}]
        with patch.object(self.hand,'transaction',return_value=nullcontext()):
            self.connection.execute.return_value.fetchone.return_value=None;self.assertIsNone(self.hand.checkpoint())
            with self.assertRaisesRegex(ConversionError,'checkpoint_unavailable'):self.hand.checkpoint(str(uuid4()))
            for index,value,code in [(3,'b'*64,'authority_mismatch'),(4,['other_writer'],'authority_mismatch'),(2,'legacy-004-31','layout_mismatch')]:
                changed=list(row);changed[index]=value;self.connection.execute.return_value.fetchone.return_value=changed
                with self.assertRaisesRegex(ConversionError,code):self.hand.checkpoint()
            self.connection.execute.return_value.fetchone.return_value=row;self.assertEqual(self.hand.checkpoint()['phase'],'prepared')

    def test_provider_list_never_accepts_duplicate_or_unbound_accounts(self):
        expected={'provider':'razorpay','account_id':'merchant123','mode':'test'}
        for value in (None,[],[expected,expected],[expected|{'mode':'other'}],[expected|{'account_id':'foreign'}],
            [expected|{'provider':'resend','mode':'test'}],[expected|{'extra':'field'}]):
            with self.assertRaisesRegex(ConversionError,'provider_binding_invalid'):self.hand.prepare(value)
        self.connection.execute.assert_not_called()
        with self.assertRaisesRegex(ConversionError,'journal_not_ready'):self.hand.enter_journal_only(str(uuid4()),object())

    def test_privileged_writer_or_schema_owner_is_never_disabled_by_conversion(self):
        layout=SimpleNamespace(structure={'relations':{'public.bookings':[]}})
        for answers,code in [([(True,True,False,False,False,False)],'writer_privileged'),
            ([(True,False,False,False,False,False),(True,)],'writer_privileged'),
            ([(True,False,False,False,False,False),(False,),(True,)],'can_change_schema'),
            ([(True,False,False,False,False,False),(False,),(False,),(True,)],'writer_is_owner')]:
            self.connection.execute.side_effect=[Mock(fetchone=lambda row=row:row) for row in answers]
            with self.assertRaisesRegex(ConversionError,code):self.hand.writer_privileges(layout)

    def test_import_refuses_unknown_columns_forbidden_targets_and_dependency_cycles(self):
        with self.assertRaisesRegex(ConversionError,'result_invalid'):self.hand.insert({})
        def translated(tables):return Translation('fixture','a'*64,tables,{}, {})
        def execute(query,params=None):
            text=str(query)
            if 'pg_constraint' in text:return Mock(fetchall=lambda:[])
            if 'pg_attribute' in text:return Mock(fetchall=lambda:[('id',)])
            return Mock()
        self.connection.execute.side_effect=execute
        for tables,code in [({'installation':[{'id':'x'}]},'target_forbidden'),({'bookings':[{'unknown':'x'}]},'columns_unrecognized'),({'bookings':[{}]},'columns_unrecognized')]:
            with self.assertRaisesRegex(ConversionError,code):self.hand.insert(translated(tables))
        self.connection.execute.side_effect=lambda *args:Mock(fetchall=lambda:[])
        with self.assertRaisesRegex(ConversionError,'target_unrecognized'):self.hand.insert(translated({'bookings':[{'id':'x'}]}))
        self.connection.execute.side_effect=lambda *args:Mock(fetchall=lambda:[('bookings','payments',['id']),('payments','bookings',['id'])])
        with self.assertRaisesRegex(ConversionError,'dependency_cycle'):self.hand.insert(translated({'bookings':[{'id':'x'}],'payments':[{'id':'x'}]}))

    def test_import_cannot_replace_existing_policy_or_resource_ownership(self):
        policy={'version':'a'*64,'specification':{'saved':True}}
        resource={'resource':'calendar','owner_email':'practice@example.test','active_client':'current','retained_clients':['current'],'grant_id':str(uuid4()),'revision':1,'updated_at':'2031-04-04T00:00:00Z'}
        def translated(table,row):return Translation('fixture','a'*64,{table:[row]},{},{})
        for table,row,existing,code in [('booking_policies',policy,({'saved':False},),'policy_collision'),
            ('google_resources',resource,('foreign@example.test','current',['current'],None),'resource_collision'),
            ('google_resources',resource,('practice@example.test','current',['current'],'already-connected'),'resource_collision')]:
            def execute(query,params=None):
                text=str(query)
                if 'pg_constraint' in text:return Mock(fetchall=lambda:[])
                if 'pg_attribute' in text:return Mock(fetchall=lambda:[(key,) for key in row])
                return Mock(fetchone=lambda:existing)
            self.connection.execute.side_effect=execute
            with self.assertRaisesRegex(ConversionError,code):self.hand.insert(translated(table,row))

    def test_abort_cannot_undo_imported_work_or_discard_buffered_notifications(self):
        with patch.object(self.hand,'transaction',return_value=nullcontext()):
            self.connection.execute.return_value.fetchone.return_value=None
            with self.assertRaisesRegex(ConversionError,'rollback_forbidden'):self.hand.abort_before_import(str(uuid4()))
            self.connection.execute.side_effect=[Mock(fetchone=lambda:('journal_only',self.bindings.installation.installation_id,'a'*64,['old_writer'])),Mock(fetchone=lambda:(True,))]
            with self.assertRaisesRegex(ConversionError,'notifications_require_resolution'):self.hand.abort_before_import(str(uuid4()))
