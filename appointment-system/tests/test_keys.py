"""Tampering, audience separation, rotation and protected output tests."""
from copy import deepcopy
import json
import unittest
from appointment_system.errors import Rejected
from appointment_system.keys import KeyRing,encode,independent,material
from .fixtures import installation

IDENTITY=installation()["installation_id"]


def document(*,purpose="receipt"):
    return {"version":1,"installation_id":IDENTITY,"environment":"test","purpose":purpose,
            "active":"k2","keys":{"k1":encode(b"1"*32),"k2":encode(b"2"*32)}}


def ring(value=None,*,purpose="receipt"):
    return KeyRing.parse(document(purpose=purpose) if value is None else value,
                         installation_id=IDENTITY,environment="test",purpose=purpose)


class KeyTests(unittest.TestCase):
    def test_rotated_ciphertext_opens_using_retained_version_and_nonce_changes(self):
        original=document();original["active"]="k1"
        archived=ring(original).seal("booking-1",b"private customer data")
        current=ring()
        self.assertEqual(current.open("booking-1",archived),b"private customer data")
        other=ring().seal("booking-1",b"private customer data")
        self.assertNotEqual(archived["nonce"],other["nonce"])
        self.assertNotIn("111111",repr(current))
        self.assertNotIn("222222",repr(current))

    def test_ciphertext_cannot_move_across_installation_environment_purpose_or_record(self):
        protected=ring().seal("booking-1",b"private")
        for field,value in [("version",True),("version",2),("installation_id","56f0ce03-75eb-494d-a31f-e89e1a73bf8d"),
                            ("environment","production"),("purpose","google-grant"),("record","booking-2"),
                            ("key_id","missing"),("nonce",""),("ciphertext","bad"),("ciphertext",encode(b"x"*16))]:
            modified=deepcopy(protected);modified[field]=value
            with self.subTest(field=field),self.assertRaisesRegex(Rejected,"protected record"):
                ring().open("booking-1",modified)
        with self.assertRaises(Rejected):
            ring().open("booking-2",protected)
        duplicate=json.dumps(protected)[:-1]+',"version":1}'
        with self.assertRaises(Rejected):
            ring().open("booking-1",duplicate)

    def test_ring_rejects_ambiguous_audience_shape_versions_duplicates_and_bytes(self):
        for field,value in [("version",True),("version",2),("environment","production"),
                            ("purpose","context"),("installation_id","00000000-0000-0000-0000-000000000000"),
                            ("active","missing"),("active",False),("keys",{}),("keys",[]),
                            ("keys",{"bad id":encode(b"1"*32)}),("keys",{"k1":"invalid"}),
                            ("keys",{"k1":encode(b"1"*31)}),
                            ("keys",{"k1":encode(b"1"*32),"k2":encode(b"1"*32)})]:
            modified=document();modified[field]=value
            with self.subTest(field=field),self.assertRaises(Rejected):
                ring(modified)
        modified=document();modified["keys"]={f"k{n}":encode(bytes([n])*32) for n in range(9)}
        with self.assertRaises(Rejected):ring(modified)
        modified=document();modified["unexpected"]=1
        with self.assertRaises(Rejected):ring(modified)
        with self.assertRaises(Rejected):ring(json.dumps(document())[:-1]+',"active":"k1"}')
        with self.assertRaises(Rejected):
            KeyRing.parse(document(),installation_id=IDENTITY,environment="test",purpose="bad purpose")
        for value in (None,123,"x"*100001,"",encode(b"x"*31),"!"*44):
            with self.subTest(value_type=type(value).__name__),self.assertRaises(Rejected):
                material(value,32)

    def test_digest_binds_record_key_and_purpose_and_compares_safely(self):
        current=ring();digest=current.digest("booking-1",b"secret")
        self.assertTrue(current.matches("booking-1",b"secret",digest))
        self.assertFalse(current.matches("booking-2",b"secret",digest))
        self.assertFalse(current.matches("booking-1",b"changed",digest))
        self.assertFalse(current.matches("booking-1",b"secret",None))
        self.assertFalse(current.matches("booking-1",b"secret",digest,key_id="missing"))
        self.assertNotEqual(current.digest("booking-1",b"secret",key_id="k1"),digest)
        for value in ("secret",b"x"*131073):
            with self.assertRaises(Rejected):current.digest("booking-1",value)
        for value in ("private",b"x"*65537):
            with self.assertRaises(Rejected):current.seal("record",value)
        with self.assertRaises(Rejected):current.seal("",b"private")

    def test_every_retained_purpose_key_must_be_independent(self):
        context=document(purpose="context");context["keys"]["k2"]=encode(b"3"*32)
        with self.assertRaises(Rejected):independent([ring(),ring(context,purpose="context")])
        context["keys"]["k1"]=encode(b"4"*32)
        independent([ring(),ring(context,purpose="context")])
        for inputs in ([],[None],[ring(),ring()],
                       [ring(),ring(document(purpose="context"),purpose="context")]):
            with self.assertRaises(Rejected):independent(inputs)
        other=document(purpose="context");other["installation_id"]="56f0ce03-75eb-494d-a31f-e89e1a73bf8d"
        other["keys"]["k2"]=encode(b"4"*32)
        foreign=KeyRing.parse(other,installation_id=other["installation_id"],environment="test",purpose="context")
        with self.assertRaises(Rejected):independent([ring(),foreign])
