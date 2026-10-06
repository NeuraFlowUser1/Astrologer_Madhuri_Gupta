"""Contained historical handover commands; no provider sends and no startup hook."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import sys

_entry=Path(__file__).absolute()
if any(path.is_symlink() for path in (_entry,*_entry.parents)):
    raise SystemExit('Contained handover links are forbidden.')
_root=_entry.parents[1]
sys.path[:0]=[str(_root),str(_root/'engine')]

from tools.conversion.handover import Handover,migration_connection
from tools.conversion.records import Bindings
from tools.conversion.source import ConversionError
from tools.conversion.operator_settings import selections,bindings


def run(action,connection,profile,release,selection,environment,*,identifier=None,expected_digest=None,baseline=None):
    """Check immutable command identity before any transition. Output has no rows."""
    if action not in ('preview','diff','checkpoint','prepare','journal-only','convert','complete','abort'):
        raise ConversionError('conversion_action_invalid')
    if (action in ('preview','diff','prepare') and identifier is not None
            or action in ('journal-only','convert','complete','abort') and identifier is None
            or action=='complete' and expected_digest is None
            or action!='complete' and expected_digest is not None
            or (action=='diff')!=(baseline is not None)):
        raise ConversionError('conversion_command_invalid')
    if action in ('preview','diff','prepare','convert'):
        bound=bindings(profile,selection,environment)
    else:
        # Inspecting an interrupted command and final readback do not require
        # decrypting old customer records or loading payment/email credentials.
        bound=Bindings(profile.installation,profile.initial_business,datetime.now(timezone.utc))
    handover=Handover(connection,bound,release,tuple(selection['writer_roles']),expected_layout=selection['source_layout'])
    if action=='preview':return handover.preview()
    if action=='diff':
        from tools.conversion.difference import compare
        return compare(baseline,handover.preview())
    if action=='checkpoint':return {'checkpoint':handover.checkpoint(identifier)}
    if action=='prepare':
        providers=[]
        for account in bound.payment_readers:
            item={'provider':'razorpay','account_id':account.merchant_id,'mode':account.mode}
            if item not in providers:providers.append(item)
        if bound.mail_mapper is not None:
            providers.append({'provider':'resend','account_id':bound.mail_mapper.connection.account_id,'mode':'live'})
        identifier=handover.prepare(providers)
    else:
        handover.checkpoint(identifier)
        if action=='journal-only':
            from appointment_system.provider_ingress import JournalCipher,JournalStore
            from appointment_system.secret_configuration import ring
            target=profile.installation.document['database_targets'].get('journal')
            if target is None:raise ConversionError('conversion_journal_not_ready')
            journal=JournalStore(environment['BOOKING_JOURNAL_DATABASE_URL'],expected_host=target['host'],
                cipher=JournalCipher(ring(environment,'BOOKING_JOURNAL_KEYS','provider-journal')))
            handover.enter_journal_only(identifier,journal)
        elif action=='convert':handover.convert(identifier)
        elif action=='complete':handover.complete(identifier,expected_digest)
        else:handover.abort_before_import(identifier)
    return {'checkpoint':handover.checkpoint(identifier)}


def main(argv=None,environment=None):
    parser=argparse.ArgumentParser(description='Preview, inspect or advance this installation’s explicit historical handover. Never pass secrets as arguments.')
    parser.add_argument('action',choices=('preview','diff','checkpoint','prepare','journal-only','convert','complete','abort'))
    parser.add_argument('--specification',required=True,help='Non-secret, reviewed handover selections JSON file.')
    parser.add_argument('--id',dest='identifier',help='Saved handover UUID; checkpoint without it reads the latest.')
    parser.add_argument('--expected-digest',help='Reviewed target digest; required only for complete.')
    parser.add_argument('--baseline',help='Saved preview JSON; required only for diff.')
    args=parser.parse_args(argv)
    source=dict(os.environ if environment is None else environment)
    try:
        from appointment_system.runtime import contained_release
        from appointment_system.configuration import load
        root,release=contained_release();profile=load(root.parent/'appointment-settings/project.json')
        path=Path(args.specification).absolute()
        if any(value.is_symlink() for value in (path,*path.parents)) or not path.is_file():
            raise ConversionError('conversion_selection_file_invalid')
        with path.open('rb') as handle:raw=handle.read(16385)
        selection=selections(raw,profile)
        baseline=None
        if args.baseline:
            from appointment_system.serialization import decode
            path=Path(args.baseline).absolute()
            if any(value.is_symlink() for value in (path,*path.parents)) or not path.is_file():
                raise ConversionError('conversion_preview_file_invalid')
            with path.open('rb') as handle:baseline=decode(handle.read(131073),maximum=131072)
        with migration_connection(source.get('BOOKING_MIGRATION_DATABASE_URL',''),profile.installation) as connection:
            result=run(args.action,connection,profile,release,selection,source,
                       identifier=args.identifier,expected_digest=args.expected_digest,baseline=baseline)
        print(json.dumps({'action':args.action,'project':profile.installation.document['project_id'],**result},sort_keys=True))
        return 0
    except (KeyboardInterrupt,EOFError):
        print('Handover command interrupted. Inspect its saved checkpoint before retrying.',file=sys.stderr)
        return 1
    except Exception as error:
        code=str(error) if isinstance(error,ConversionError) and re.fullmatch(r'(?:conversion|legacy)_[a-z0-9_]{1,100}',str(error)) else 'conversion_command_failed'
        print(json.dumps({'status':'failed','code':code,'next_action':'inspect_checkpoint_before_retry'}),file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
