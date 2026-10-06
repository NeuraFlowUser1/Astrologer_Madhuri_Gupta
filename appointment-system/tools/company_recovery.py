"""Owner-only local company access recovery; no public reset or secret output."""
import argparse
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
from uuid import UUID
import warnings

_entry=Path(__file__).absolute()
if any(path.is_symlink() for path in (_entry,*_entry.parents)):
    raise SystemExit('Contained recovery links are forbidden.')
_root=_entry.parents[1]
sys.path[:0]=[str(_root),str(_root/'engine')]

from appointment_system.company_auth import password_hash,username,verify
from appointment_system.serialization import canonical
from tools.setup import SetupError,owner,installed


def inspect(connection,installation,name):
    name=username(name)
    with owner(connection,installation):
        installed(connection,installation)
        row=connection.execute('SELECT credential_revision,enabled FROM appointment_system.company_credentials WHERE username=%s',(name,)).fetchone()
        if row is None:
            raise SetupError('recovery_account_missing')
        return {'status':'inspected','credential_revision':row[0],'enabled':row[1]}


def recover(connection,installation,name,secret,*,operation,expected_revision,reason):
    name=username(name)
    try:valid=type(operation) is str and str(UUID(operation))==operation and bool(UUID(operation).int)
    except (ValueError,TypeError,AttributeError):valid=False
    if (not valid or type(expected_revision) is not int or not 1<=expected_revision<2**63-1
        or type(reason) is not str or not 10<=len(reason)<=300 or not reason.strip()
        or any(ord(char)<32 or ord(char)==127 for char in reason)):
        raise SetupError('recovery_request_invalid')
    encoded=password_hash(secret)
    body=hashlib.sha256(canonical({'username':name,'expected_revision':expected_revision,'reason':reason})).hexdigest()
    with owner(connection,installation):
        installed(connection,installation)
        row=connection.execute('SELECT subject,credential_revision,enabled,password_hash FROM appointment_system.company_credentials WHERE username=%s FOR UPDATE',(name,)).fetchone()
        if row is None:
            raise SetupError('recovery_account_missing')
        subject,revision,enabled,current_hash=row
        if not enabled:
            raise SetupError('recovery_disabled_account_requires_review')
        prior=connection.execute('SELECT subject,body_hash,resulting_revision FROM appointment_system.company_password_recoveries WHERE operation_id=%s',(operation,)).fetchone()
        if prior:
            if prior!=(subject,body,revision) or not verify(current_hash,secret):
                raise SetupError('recovery_operation_conflict')
            return {'status':'existing','credential_revision':revision,'changed':False}
        if revision!=expected_revision:
            raise SetupError('recovery_revision_conflict')
        result=connection.execute('SELECT appointment_system.provision_company_password(%s,%s)',(name,encoded)).fetchone()
        if result!=(subject,):
            raise SetupError('recovery_identity_changed')
        connection.execute('INSERT INTO appointment_system.company_password_recoveries(operation_id,subject,previous_revision,resulting_revision,operator_role,reason,body_hash) VALUES(%s,%s,%s,%s,session_user,%s,%s)',
            (operation,subject,revision,revision+1,reason,body))
        return {'status':'recovered','credential_revision':revision+1,'changed':True}


def main(argv=None,environment=None):
    parser=argparse.ArgumentParser(description='Protected company password recovery in this installation only.')
    parser.add_argument('action',choices=('inspect','recover'))
    parser.add_argument('--operation-id');parser.add_argument('--expected-revision',type=int);parser.add_argument('--reason')
    args=parser.parse_args(argv)
    source=os.environ if environment is None else environment
    try:
        from appointment_system.runtime import contained_release
        from appointment_system.configuration import load
        from tools.conversion.handover import migration_connection
        root,_=contained_release();profile=load(root.parent/'appointment-settings/project.json')
        if not sys.stdin.isatty():raise SetupError('setup_private_terminal_required')
        name=input('Existing company username: ')
        secret=None
        if args.action=='recover':
            if args.operation_id is None or args.expected_revision is None or args.reason is None:
                raise SetupError('recovery_request_invalid')
            with warnings.catch_warnings():
                warnings.simplefilter('error',getpass.GetPassWarning)
                try:
                    secret=getpass.getpass('Replacement password (15–128 characters): ')
                    repeated=getpass.getpass('Repeat replacement password: ')
                except getpass.GetPassWarning:raise SetupError('setup_private_terminal_required') from None
            if secret!=repeated:raise SetupError('setup_password_mismatch')
        with migration_connection(source.get('BOOKING_MIGRATION_DATABASE_URL',''),profile.installation) as connection:
            if args.action=='inspect':result=inspect(connection,profile.installation,name)
            else:result=recover(connection,profile.installation,name,secret,operation=args.operation_id,
                expected_revision=args.expected_revision,reason=args.reason)
        print(json.dumps({'project':profile.installation.document['project_id'],**result},sort_keys=True))
        return 0
    except (KeyboardInterrupt,EOFError):
        print('Recovery cancelled.',file=sys.stderr);return 1
    except Exception as error:
        print(json.dumps({'status':'failed','code':str(error) if isinstance(error,SetupError) else 'recovery_failed'}),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
