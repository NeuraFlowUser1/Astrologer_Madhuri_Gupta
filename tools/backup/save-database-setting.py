"""Receive the approved backup URL without echo; verify access and save to GitHub."""
import argparse
from database_setting import main
from envelope import BackupError

if __name__=='__main__':
    try:
        parser=argparse.ArgumentParser()
        parser.add_argument('--wait-seconds',type=int,default=0)
        args=parser.parse_args()
        main(args.wait_seconds)
    except BackupError as error:raise SystemExit(str(error)) from None
    except Exception:raise SystemExit('backup_database_setup_failed_no_private_values_logged') from None
