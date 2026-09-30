import io
import unittest
from envelope import BackupError, encrypt, decrypt, decode_key

class EnvelopeTests(unittest.TestCase):
    key=b'x'*32
    metadata={'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':'2026-09-29'}
    def encoded(self,data=b'PGDMP'+b'synthetic data'*100000):
        out=io.BytesIO();encrypt(io.BytesIO(data),out,self.key,self.metadata);return out.getvalue()
    def test_roundtrip_and_no_plaintext(self):
        plain=b'PGDMP'+b'synthetic data'*100000
        encoded=self.encoded(plain)
        self.assertNotIn(b'synthetic data',encoded)
        self.assertEqual(decrypt(io.BytesIO(encoded),self.key),self.metadata)
        restored=io.BytesIO();decrypt(io.BytesIO(encoded),self.key,restored)
        self.assertEqual(restored.getvalue(),plain)
    def test_tamper_truncation_wrong_key_and_append_fail(self):
        data=self.encoded()
        for candidate,key in [(data[:-1],self.key),(data+b'x',self.key),(data[:50]+bytes([data[50]^1])+data[51:],self.key),(data,b'y'*32)]:
            with self.assertRaises(BackupError):decrypt(io.BytesIO(candidate),key)
    def test_key_must_be_exact_canonical_32_bytes(self):
        self.assertEqual(len(decode_key('eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHh4eHg=')),32)
        for value in ['', 'not-a-key', 'A'*44]:
            with self.assertRaises(BackupError):decode_key(value)

if __name__=='__main__':unittest.main()
