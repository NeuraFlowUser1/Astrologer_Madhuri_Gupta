"""One-time OFF display setup, using maintenance authority only."""
import argparse,json,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'engine'))

def main(argv=None,environment=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--operation',required=True,help='Saved non-secret operation ID; reuse after a lost reply.')
    args=parser.parse_args(argv)
    source=dict(os.environ if environment is None else environment)
    try:
        from appointment_system.runtime import contained_release
        from appointment_system.configuration import load,worker_origin
        root,_=contained_release();profile=load(root.parent/'appointment-settings/project.json')
        from appointment_system.control_recovery import RecoveryDatabase,RecoverySettings,ProjectionInitialization,_operation
        from appointment_system.projection import key
        from appointment_system.connection import checked_config
        import certifi,psycopg
        operation=_operation(args.operation)
        settings=RecoverySettings(key(source['BOOKING_CONTROL_READ_KEY']),key(source['BOOKING_CONTROL_RECONCILE_KEY']),
                                  key(source['BOOKING_CONTROL_PUBLISH_KEY']),worker_origin())
        target=profile.facts()['database_targets']['maintenance']
        config=checked_config(source['BOOKING_MAINTENANCE_DATABASE_URL'],target['host'],purpose='maintenance')
        config.update(sslmode='verify-full',sslrootcert=certifi.where(),channel_binding='require',
                      connect_timeout=3,prepare_threshold=None,autocommit=True)
        with psycopg.connect(**config) as connection:
            result=ProjectionInitialization(RecoveryDatabase(connection),settings).run(operation)
        print(json.dumps({'project':profile.facts()['project_id'],**result},sort_keys=True))
        return 0
    except (Exception,KeyboardInterrupt):
        print('Initial display setup failed. Check the saved OFF state, maintenance settings and operation ID. No booking was enabled.',file=sys.stderr)
        return 1

if __name__=='__main__':raise SystemExit(main())
