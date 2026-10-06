from copy import deepcopy
import unittest

from appointment_system.errors import Rejected
from appointment_system.settings import BusinessSettings, Installation, boolean, email, identifier, origin
from .fixtures import business, changed, installation


class SettingsTests(unittest.TestCase):
    def rejected(self, parser, value):
        with self.assertRaises(Rejected): parser(value)

    def test_immutable_facts_and_two_verification_profiles(self):
        source = installation()
        saved = Installation.parse(source)
        source['label'] = 'changed'
        read = saved.document
        read['label'] = 'changed again'
        self.assertEqual(saved.document['label'], 'Example Practice')
        self.assertEqual(saved.project_id, 'example-practice')
        self.assertEqual(saved.installation_id, installation()['installation_id'])
        self.assertEqual(saved.environment, 'test')
        for otp in (False, True):
            for question in (False, True):
                saved_business = BusinessSettings.parse(business(booking_otp=otp, per_question=question))
                self.assertEqual(saved_business.document['booking_verification']['email'], otp)
                self.assertEqual(saved_business.public_services(), [{'id': 'consultation', 'name': 'Consultation'}])
        original = business()
        frozen = BusinessSettings.parse(original)
        original['services'][0]['pricing']['amount_paise'] = 1
        self.assertEqual(frozen.document['services'][0]['pricing']['amount_paise'], 210000)

    def test_installation_rejects_wrong_identity_provider_and_routes(self):
        base = installation()
        changes = {'version': True, 'installation_id': 'bad', 'project_id': 'Other Client',
                   'label': '', 'environment': 'preview', 'origin': 'http://foreign.example',
                   'aliases': [base['origin']], 'database_targets': {},
                   'owners': {'client_email': 'same@example.test', 'agency_email': 'same@example.test'},
                   'providers': {'payment': 'unknown', 'calendar': 'google', 'email': 'resend', 'sms': None},
                   'sender': {'name': 'Name\nInjection', 'email': 'x@example.test', 'reply_to': 'x@example.test'},
                   'worker': {'name': '../other', 'origin': 'https://worker.example.test'}, 'surfaces': []}
        for key, value in changes.items():
            with self.subTest(key=key): self.rejected(Installation.parse, changed(base, key, value))
        for key, value in {'host': '../other', 'role': 'postgres;drop', 'database': 'Other', 'port': 0, 'pooling': 1}.items():
            data = deepcopy(base); data['database_targets']['web'][key] = value
            self.rejected(Installation.parse, data)
        for path in ('//foreign.test', '/%2fbooking', '/a/../booking', '/a\\b', '/a?secret', '/a#booking', 'booking'):
            self.rejected(Installation.parse, changed(base, 'surfaces', [{'path': path, 'class': 'booking'}]))
        self.rejected(Installation.parse, changed(base, 'surfaces', [base['surfaces'][0]] * 2))
        self.rejected(Installation.parse, changed(base, 'surfaces', [{'path': '/', 'class': 'unknown'}]))
        self.rejected(Installation.parse, changed(base, 'aliases', ['https://a.example.test'] * 2))
        self.rejected(Installation.parse, changed(base, 'owners', {'client_email': 'not-email', 'agency_email': 'a@example.test'}))
        data = deepcopy(base); data['database_targets']['alien'] = data['database_targets']['web']
        self.rejected(Installation.parse, data)

    def test_origin_email_boolean_and_identifier_boundaries(self):
        self.assertEqual(origin('http://127.0.0.1:8081', 'test'), 'http://127.0.0.1:8081')
        self.assertEqual(origin('https://practice.example.test', 'production'), 'https://practice.example.test')
        for url in ('http://practice.example.test', 'https://localhost', 'https://a.example.test:443',
                    'https://a.example.test/a', 'https://user:pass@a.example.test', 'https://a.example.test?q=1',
                    'https://UPPER.example.test', 'https://[', 'https://a.example.test:bad'):
            with self.assertRaises(Rejected): origin(url, 'production')
        self.assertEqual(email('Person@EXAMPLE.TEST'), 'person@example.test')
        self.assertTrue(boolean(True))
        self.assertEqual(identifier('service-1'), 'service-1')
        for function, value in ((email, 'a@b'), (boolean, 1), (identifier, 'a_b')):
            self.rejected(function, value)

    def test_business_bounds_types_and_supported_capabilities(self):
        base = business()
        for field, value in (('version', 0), ('timezone', 'Wrong/Timezone'), ('slot_step_minutes', 7),
                             ('notice_minutes', -1), ('horizon_days', 366), ('buffer_before_minutes', True),
                             ('buffer_after_minutes', 121), ('services', []), ('weekly_windows', []),
                             ('required_contacts', ['phone']), ('required_contacts', ['email', 'email']),
                             ('booking_verification', {'email': True, 'sms': True}),
                             ('booking_verification', {'email': 1, 'sms': False}), ('meeting', 'unknown')):
            self.rejected(BusinessSettings.parse, changed(base, field, value))
        for field, value in (('id', 'bad/id'), ('name', ''), ('enabled', 1), ('duration_minutes', 31),
                             ('duration_minutes', 0), ('required_preparation', ['unsupported']),
                             ('pricing', {'kind': 'fixed', 'amount_paise': 0, 'maximum_questions': 1}),
                             ('pricing', {'kind': 'fixed', 'amount_paise': 100, 'maximum_questions': 2}),
                             ('pricing', {'kind': 'unknown', 'amount_paise': 100, 'maximum_questions': 1}),
                             ('pricing', {'kind': 'per_question', 'amount_paise': 2147483647, 'maximum_questions': 2})):
            data = deepcopy(base); data['services'][0][field] = value
            self.rejected(BusinessSettings.parse, data)
        self.rejected(BusinessSettings.parse, changed(base, 'services', base['services'] * 2))
        for window in ({'weekday': 7, 'start': '10:00', 'end': '12:00'},
                       {'weekday': 0, 'start': '24:00', 'end': '24:00'},
                       {'weekday': 0, 'start': '9:00', 'end': '12:00'},
                       {'weekday': 0, 'start': '12:00', 'end': '10:00'}):
            self.rejected(BusinessSettings.parse, changed(base, 'weekly_windows', [window]))
        self.rejected(BusinessSettings.parse, changed(base, 'weekly_windows', base['weekly_windows'] * 2))
        midnight = changed(base, 'weekly_windows', [{'weekday': 0, 'start': '23:00', 'end': '24:00'}])
        self.assertEqual(BusinessSettings.parse(midnight).document['weekly_windows'][0]['end'], '24:00')
        for budget in ({'daily': 10, 'rolling': 600, 'verification_daily': 11, 'verification_rolling': 0},
                       {'daily': 20, 'rolling': 10, 'verification_daily': 0, 'verification_rolling': 0},
                       {'daily': 20, 'rolling': 600, 'verification_daily': 0, 'verification_rolling': 601}):
            self.rejected(BusinessSettings.parse, changed(base, 'email_budget', budget))
