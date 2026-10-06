"""Unreadable permission is retained honestly; only verified consent replaces it."""
from copy import deepcopy
from unittest.mock import patch
import unittest
from appointment_system.configuration import profile
from appointment_system.google_oauth import GoogleFailure
from appointment_system.google_resources import Resources,ResourceCipher
from appointment_system.serialization import canonical
from appointment_system.settings import Installation
from tools.conversion.grants import GrantTransfer
from tools.conversion.operator_settings import selections,bindings
from tools.conversion.reauthorization import FORMAT,PURPOSE
from tools.conversion.source import ConversionError,catalogue
from .fixtures import installation
from .handover_configuration import protected
from .test_keys import ring
from .test_google_resources import spec,WEB
from . import test_conversion_grants as prior
NOW=prior.NOW


class CalendarReauthorization(unittest.TestCase):
    def setUp(self):
        fixture=prior.HistoricalGoogleGrants();fixture.setUp()
        self.row=fixture.calendar(bare=True)
        self.resources=Resources(spec(),ResourceCipher(ring(purpose='google-resource-grant')))
        self.transfer=GrantTransfer(Installation.parse(installation()),self.resources,
            calendar_client=WEB,calendar_reauthorization=True)
        self.layout=next(item for item in catalogue() if item.identifier=='legacy-003-16')

    def test_no_old_key_is_needed_but_retained_record_never_becomes_a_refresh_token(self):
        with patch.object(self.resources.cipher,'legacy_value',side_effect=AssertionError('must not decrypt')):
            result=self.transfer(self.layout,'google_connection',[self.row])
        record=result['google_resource_grants'][0]
        self.assertEqual(record['grant_format'],FORMAT)
        self.assertEqual(record['last_error_code'],'google_reconnect_required')
        self.assertEqual(record['subject'],self.row['google_subject'])
        self.assertEqual(record['owner_email'],self.row['calendar_id'])
        self.assertEqual(record['client_id'],WEB)
        retained=self.resources.cipher.protected.open('google-resource-grant:'+record['id'],
            record['encrypted_grant'],purpose=PURPOSE)
        self.assertEqual(retained['encrypted_legacy_grant'],self.row['refresh_token_encrypted'])
        self.assertNotIn(self.row['refresh_token_encrypted'],record['encrypted_grant'])
        for error in (None,'google_reconnect_required'):
            with self.assertRaisesRegex(GoogleFailure,'google_reconnect_required'):
                self.resources.cipher.open(record|{'grant_id':record['id'],'last_error_code':error},'calendar',now=NOW)
        # Changing only the declared format cannot turn retained history into authority.
        with self.assertRaisesRegex(GoogleFailure,'google_saved_grant_invalid'):
            self.resources.cipher.open(record|{'grant_id':record['id'],'grant_format':'v1'},'calendar',now=NOW)

    def test_wrong_identity_scope_cipher_size_and_ambiguous_reader_are_refused(self):
        for changes in ({'google_subject':''},{'google_subject':'bad\nsubject'},
                {'calendar_id':'foreign@example.test'},{'scopes':'openid'},
                {'refresh_token_encrypted':'short'},{'refresh_token_encrypted':'x'*32769},
                {'refresh_token_encrypted':'x'*32768}):
            with self.subTest(fields=list(changes)),self.assertRaises((ConversionError,ValueError)):
                self.transfer.calendar(self.row|changes)
        for flag in (1,'yes',None):
            with self.assertRaises(ConversionError):
                GrantTransfer(Installation.parse(installation()),self.resources,calendar_reauthorization=flag)
        with self.assertRaises(ConversionError):
            GrantTransfer(Installation.parse(installation()),self.resources,calendar_reauthorization=True,formats={'calendar-bare':'old'})
        # Existing declared client can be retained without being the active consent client.
        from .test_google_resources import DESKTOP
        self.transfer.calendar_client=DESKTOP
        with self.assertRaises(ConversionError):self.transfer.calendar(self.row)

    def test_opt_in_is_explicit_published_source_only_and_cannot_name_a_fake_reader(self):
        selected,env=protected('003',integrations=True)
        selected['google'].update(resource_formats={},full_grant_reader=None,calendar_reauthorization=True)
        env.pop('BOOKING_LEGACY_RESOURCE_READERS');env.pop('BOOKING_LEGACY_GOOGLE_GRANTS')
        parsed=selections(canonical(selected),profile());bound=bindings(profile(),parsed,env)
        result=bound.resource_mapper(self.layout,'google_connection',[self.row])
        self.assertEqual(result['google_resource_grants'][0]['grant_format'],FORMAT)
        for change in ({'calendar_reauthorization':'true'},{'resource_formats':{'calendar-bare':'old'}},
                       {'full_grant_reader':'old'},{'calendar_client':None}):
            bad=deepcopy(selected);bad['google'].update(change)
            with self.assertRaises(ConversionError):selections(canonical(bad),profile())
        sarsa,_=protected('004',integrations=True);sarsa['google'].update(
            calendar_reauthorization=True,resource_formats={},full_grant_reader=None)
        with self.assertRaises(ConversionError):selections(canonical(sarsa),profile())
        for layout in catalogue():
            if layout.identifier!=self.layout.identifier:
                with self.assertRaises(ConversionError):self.transfer(layout,'google_connection',[])
        with self.assertRaises(ConversionError):self.transfer(self.layout,'sheet_owner_grants',[])
        declared=prior.readers();declared['readers'][FORMAT]=next(iter(declared['readers'].values()))
        with self.assertRaises(ValueError):ResourceCipher(ring(purpose='google-resource-grant'),declared)
