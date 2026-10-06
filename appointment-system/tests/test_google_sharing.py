"""Access checks run before any Google Sheets read/write; no live provider calls."""
from copy import deepcopy
from uuid import uuid4
import unittest

from appointment_system.google_sharing import approvals, check_permissions
from appointment_system.google_workspace import WorkspaceFailure, FILE_FIELDS
from . import test_google_workspace as fixture


class WorkbookSharing(unittest.TestCase):
    def setUp(self):
        self.proof = fixture.WorkspaceTests(); self.proof.setUp()
        self.owner = self.proof.access.grant.email
        self.permission = dict(type='user', role='owner', emailAddress=self.owner)
        self.named = dict(type='user', role='writer', emailAddress='writer@example.test')

    def test_owner_only_and_exact_named_approval_pass_without_changing_sharing(self):
        for approved, actual in [([], [self.permission]), ([self.named], [self.named, self.permission]),
                ([self.named], [self.permission])]:
            check_permissions(actual, self.owner, approved)
        check_permissions([self.permission | {'emailAddress': self.owner.upper()}], self.owner, [])
        self.assertIn('emailAddress,deleted,pendingOwner', FILE_FIELDS)

    def test_unknown_sharing_bad_owner_or_incomplete_provider_evidence_is_refused(self):
        for actual in [None, [], [self.permission] * 18, [self.permission] * 2,
                [self.named], [self.permission, self.named], [None],
                [self.permission | {'role': 'writer'}], [self.permission | {'emailAddress': None}],
                [self.permission | {'pendingOwner': True}], [self.permission | {'deleted': True}],
                [self.permission, {'type': 'anyone', 'role': 'reader'}],
                [self.permission, {'type': 'domain', 'role': 'reader'}],
                [self.permission, self.named | {'type': 'group'}]]:
            with self.subTest(actual=actual), self.assertRaises(ValueError):
                check_permissions(actual, self.owner, [])

    def test_approvals_never_allow_owner_transfer_duplicates_or_unnamed_access(self):
        for approved in [None, {}, [self.named] * 17, [self.named] * 2, [None],
                [self.named | {'emailAddress': self.owner}], [self.named | {'emailAddress': 'bad'}],
                [self.named | {'emailAddress': 'a' * 255 + '@example.test'}],
                [self.named | {'role': 'owner'}], [self.named | {'role': 'organizer'}],
                [self.named | {'type': 'anyone'}], [self.named | {'extra': True}]]:
            with self.subTest(approved=approved), self.assertRaises(ValueError):
                approvals(approved, self.owner)
        approved = [self.named | {'type': 'group', 'role': 'reader'}]
        check_permissions([self.permission, approved[0]], self.owner, approved)
        with self.assertRaises(ValueError):
            check_permissions([approved[0]], self.owner, approved)
        with self.assertRaises(ValueError):
            check_permissions([self.permission, self.named], self.owner, approved)

    def test_unapproved_user_or_group_prevents_sheet_io_and_keeps_existing_file_untouched(self):
        for share in [self.named, self.named | {'type': 'group'}, self.named | {'role': 'reader'}]:
            file = deepcopy(self.proof.file); file['permissions'].append(share)
            workspace = self.proof.workspace([(200, file)])
            with self.assertRaisesRegex(WorkspaceFailure, 'sharing_mismatch'):
                workspace.prepare_workbook(file['id'], self.proof.intent)
        self.assertEqual(len(self.proof.requests), 3)
        self.assertTrue(all(request.method == 'GET' and '/drive/' in request.url.path
                            for request in self.proof.requests))

    def test_approval_is_bound_to_the_saved_volume_and_exact_permission_role(self):
        workspace = self.proof.workspace([])
        saved = dict(role='client', volume_number=1, layout_version=1, generation=str(uuid4()),
                     intent=self.proof.intent, approved_permissions=[self.named])
        workspace.bind_volume(saved)
        saved['approved_permissions'].clear()
        file = deepcopy(self.proof.file); file['permissions'].append(self.named)
        self.assertEqual(workspace.validate_workbook(file, self.proof.intent), file['id'])
        file['permissions'][-1] = self.named | {'role': 'reader'}
        with self.assertRaisesRegex(WorkspaceFailure, 'sharing_mismatch'):
            workspace.validate_workbook(file, self.proof.intent)
        with self.assertRaisesRegex(WorkspaceFailure, 'identity_invalid'):
            workspace.bind_volume(saved | {'approved_permissions': [self.permission]})


if __name__ == '__main__': unittest.main()
