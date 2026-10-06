"""Bounded company password hashing, durable admission and opaque sessions."""
from dataclasses import dataclass,field
import hashlib
import re
import secrets
from threading import BoundedSemaphore
from argon2 import PasswordHasher,Type
from argon2.exceptions import InvalidHashError,VerificationError
from .errors import Rejected
from .serialization import text

HASHER=PasswordHasher(time_cost=2,memory_cost=19456,parallelism=1,hash_len=32,salt_len=16,type=Type.ID)
HASH_SLOTS=BoundedSemaphore(2)
HASH_PATTERN=re.compile(r"\$argon2id\$v=19\$m=19456,t=2,p=1\$[A-Za-z0-9+/]{22}\$[A-Za-z0-9+/]{43}\Z")
DUMMY_HASH=HASHER.hash(secrets.token_urlsafe(32))
COOKIE="__Host-booking-company"
CSRF_COOKIE="__Host-booking-company-csrf"


def username(value):
    if type(value) is not str:
        raise Rejected("company_login_failed","Please check your username and password.",401)
    normalized=value.lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_.-]{2,63}",normalized):
        raise Rejected("company_login_failed","Please check your username and password.",401)
    return normalized


def password(value):
    if type(value) is not str or not 15<=len(value)<=128 or any(ord(c)<32 or ord(c)==127 for c in value):
        raise Rejected("company_login_failed","Please check your username and password.",401)
    return value


def password_hash(value):
    value=password(value)
    if not HASH_SLOTS.acquire(blocking=False):
        raise Rejected('please_wait','Please wait briefly before changing the password.',429)
    try:return HASHER.hash(value)
    finally:HASH_SLOTS.release()


def verify(encoded,value):
    valid_encoded=type(encoded) is str and HASH_PATTERN.fullmatch(encoded) is not None
    candidate=encoded if valid_encoded else DUMMY_HASH
    if not HASH_SLOTS.acquire(blocking=False):
        raise Rejected("please_wait","Please wait briefly before signing in.",429)
    try:
        try:
            matched=HASHER.verify(candidate,password(value))
        except (VerificationError,InvalidHashError):
            matched=False
        return matched and valid_encoded
    finally:
        HASH_SLOTS.release()


@dataclass(frozen=True,repr=False)
class Credentials:
    database:object=field(repr=False)
    settings:object=field(repr=False)

    def login(self,name,secret,risk):
        name=username(name);password(secret)
        result=self.database.call("SELECT appointment_system.company_login_begin(%s,%s,%s)",
             (name,self.settings.digest("login-risk",risk),self.settings.digest("login-username",name)))
        if result.get("code")=="please_wait":
            raise Rejected("please_wait","Please wait before signing in again.",429)
        matched=verify(result.get("password_hash"),secret)
        token=secrets.token_urlsafe(32);csrf=self.settings.digest("csrf",token)
        accepted=self.database.call("SELECT appointment_system.company_login_finish(%s,%s,%s,%s,%s)",
             (result["attempt_id"],result.get("credential_revision"),matched,
              self.settings.digest("session",token),hashlib.sha256(csrf.encode()).hexdigest()))
        if not accepted:
            raise Rejected("company_login_failed","Please check your username and password.",401)
        return token,csrf

    def session(self,token):
        if type(token) is not str or not re.fullmatch(r"[A-Za-z0-9_-]{43}",token):
            raise Rejected("company_session_required","Please sign in to company controls.",401)
        digest=self.settings.digest("session",token)
        if not self.database.call("SELECT appointment_system.company_session_touch(%s)",(digest,)):
            raise Rejected("company_session_required","Please sign in to company controls.",401)
        return digest

    def credential_action(self,token,csrf,secret,risk,new_password=None):
        password(secret)
        if new_password is not None:password(new_password)
        action='password' if new_password is not None else 'reauthenticate'
        result=self.database.call('SELECT appointment_system.company_credential_begin(%s,%s,%s,%s)',
             (token,csrf,self.settings.digest('login-risk',risk),action))
        if result.get('code')=='please_wait':
            raise Rejected('please_wait','Please wait before trying again.',429)
        matched=verify(result.get('password_hash'),secret)
        replacement=password_hash(new_password) if matched and new_password is not None else None
        fresh=secrets.token_urlsafe(32);fresh_csrf=self.settings.digest('csrf',fresh)
        accepted=self.database.call('SELECT appointment_system.company_credential_finish(%s,%s,%s,%s,%s,%s,%s,%s,%s)',
             (token,csrf,result['attempt_id'],result.get('credential_revision'),matched,action,replacement,
              self.settings.digest('session',fresh),hashlib.sha256(fresh_csrf.encode()).hexdigest()))
        if not accepted:
            raise Rejected('company_login_failed','Please check your password and sign in again if needed.',401)
        return fresh,fresh_csrf
