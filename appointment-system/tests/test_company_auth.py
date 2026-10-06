"""Password hashing, uniform rejection and bounded hashing work."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from appointment_system.company_auth import Credentials,HASHER,HASH_PATTERN,username,password,password_hash,verify
from appointment_system.errors import Rejected


class HashTests(unittest.TestCase):
    def test_hash_has_bounded_parameters_and_verifies_only_the_original_password(self):
        encoded=password_hash("Synthetic company password 004")
        self.assertIsNotNone(HASH_PATTERN.fullmatch(encoded))
        self.assertTrue(verify(encoded,"Synthetic company password 004"))
        self.assertFalse(verify(encoded,"Synthetic company password 003"))
        self.assertFalse(verify(None,"Synthetic company password 004"))
        self.assertFalse(verify("$argon2id$v=19$m=999999999,t=2,p=1$bad","Synthetic company password 004"))

    def test_username_password_bounds_and_hash_capacity_are_enforced(self):
        self.assertEqual(username("Company.Owner"),"company.owner")
        for name in (None,"ab","owner ","a"*65,"écompany","<owner>"):
            with self.assertRaises(Rejected):username(name)
        for secret in (None,"short","p"*129,"p"*15+"\n","p"*15+"\x7f"):
            with self.assertRaises(Rejected):password(secret)
        with patch("appointment_system.company_auth.HASH_SLOTS") as slots:
            slots.acquire.return_value=False
            with self.assertRaises(Rejected) as failure:
                verify(None,"Synthetic company password 004")
            self.assertEqual(failure.exception.status,429)

    def test_rejected_login_and_lost_finish_never_invent_a_session(self):
        class DB:
            stage=0
            def call(self,statement,parameters):
                self.stage+=1
                if "login_begin" in statement:
                    return {"attempt_id":"synthetic","credential_revision":1,"password_hash":None}
                return False
        db=DB();settings=SimpleNamespace(digest=lambda purpose,value:"a"*64)
        with self.assertRaises(Rejected):
            Credentials(db,settings).login("company.owner","Synthetic company password 004","source")
        self.assertEqual(db.stage,2)
        class Limited:
            def call(self,*args):
                return {"code":"please_wait"}
        with self.assertRaises(Rejected) as rejected:
            Credentials(Limited(),settings).login("company.owner","Synthetic company password 004","source")
        self.assertEqual(rejected.exception.status,429)

    def test_successful_session_and_cookie_validation(self):
        encoded=password_hash("Synthetic company password 004")
        class DB:
            def call(self,statement,parameters):
                if "login_begin" in statement:
                    return {"attempt_id":"synthetic","credential_revision":1,"password_hash":encoded}
                return True
        settings=SimpleNamespace(digest=lambda purpose,value:"a"*64)
        credentials=Credentials(DB(),settings)
        token,csrf=credentials.login("company.owner","Synthetic company password 004","source")
        self.assertEqual(len(token),43);self.assertEqual(len(csrf),64)
        self.assertEqual(credentials.session(token),"a"*64)
        for token in (None,"short","x"*43+"=","/"*43):
            with self.assertRaises(Rejected):credentials.session(token)
        class Expired:
            def call(self,*args):return False
        with self.assertRaises(Rejected):Credentials(Expired(),settings).session("a"*43)
