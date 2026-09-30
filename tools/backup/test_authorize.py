import hashlib
import base64
import unittest
from urllib.parse import parse_qs,urlsplit
from authorize import authorization_url,callback_code,SCOPE
from envelope import BackupError

class ConsentTests(unittest.TestCase):
    def test_request_is_scoped_pkce_and_no_secret_in_url(self):
        verifier='v'*64
        url=authorization_url({'client_id':'synthetic.apps.googleusercontent.com','client_secret':'never-in-url'},'state',verifier,'http://127.0.0.1:12345/callback')
        q=parse_qs(urlsplit(url).query)
        self.assertNotIn('never-in-url',url)
        self.assertEqual(q['scope'],[SCOPE]);self.assertEqual(q['login_hint'],['sarsajyotish@gmail.com'])
        self.assertEqual(q['code_challenge_method'],['S256'])
        self.assertEqual(q['code_challenge'],[base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip('=')])
    def test_callback_binding_denial_and_duplicate_parameters(self):
        self.assertEqual(callback_code('/callback?state=right&code=synthetic','right'),'synthetic')
        for path in ['/callback?state=wrong&code=x','/other?state=right&code=x','/callback?state=right&state=wrong&code=x','/callback?state=right&code=x&code=y','/callback?state=right&error=access_denied']:
            with self.assertRaises(BackupError):callback_code(path,'right')

if __name__=='__main__':unittest.main()
