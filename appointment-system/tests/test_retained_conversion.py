"""A recognised experimental schema cannot claim a proved privacy handover."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock
from tools.conversion.retained import prepare
from tools.conversion.source import ConversionError


class RetainedConversionBoundaries(TestCase):
    def test_published_accepted_only_format_does_not_get_an_abandoned_enquiry_erase_path(self):
        connection=Mock()
        prepare(connection,SimpleNamespace(identifier='legacy-003-16'),'synthetic-handover')
        connection.execute.assert_not_called()

    def test_unproved_layouts_cannot_change_source_permissions_or_finish_privacy_setup(self):
        for name in ('legacy-003-40','legacy-004-52','foreign-layout'):
            connection=Mock()
            with self.subTest(layout=name),self.assertRaisesRegex(ConversionError,'retention_layout_unproved'):
                prepare(connection,SimpleNamespace(identifier=name),'synthetic-handover')
            connection.execute.assert_not_called()
