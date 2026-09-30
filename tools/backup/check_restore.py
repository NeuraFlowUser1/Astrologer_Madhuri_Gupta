"""Explicit local restore proof with synthetic data; never connects to Neon/Drive."""
import hashlib
import os
from pathlib import Path
import secrets
import subprocess
import tempfile
import time
from envelope import encrypt
from postgres import IMAGE, ROOT, restore_check


def main():
    name='sarsa-004-backup-proof-'+secrets.token_hex(8)
    try:
        subprocess.run(['docker','run','-d','--name',name,'--network','none',
            '-e','POSTGRES_HOST_AUTH_METHOD=trust','-e','POSTGRES_DB=neondb',IMAGE],
            check=True,stdout=subprocess.DEVNULL,timeout=120)
        for _ in range(60):
            if subprocess.run(['docker','exec',name,'pg_isready','-U','postgres','-d','neondb'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
            time.sleep(1)
        else:raise RuntimeError('Synthetic database did not start')
        sql=['docker','exec','-i',name,'psql','-U','postgres','-d','neondb','-v','ON_ERROR_STOP=1']
        migrations=sorted((ROOT/'backend/booking_engine/migrations').glob('*.sql'))
        for migration in migrations:
            source=migration.read_bytes()
            ledger=("\nINSERT INTO sarsa_booking.schema_migrations(version,sha256) VALUES ('"+
                migration.name+"','"+hashlib.sha256(source).hexdigest()+"');\n").encode()
            subprocess.run(sql,input=source+ledger,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        # A real row proves this is a data restore as well as a schema restore.
        subprocess.run(sql,input=b"INSERT INTO sarsa_booking.request_limits(scope,key_digest,window_start,attempts,expires_at) VALUES ('context','aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',now(),1,now()+interval '1 hour');",check=True,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        key=os.urandom(32)
        with tempfile.TemporaryDirectory(prefix='sarsa-backup-proof-') as directory:
            path=Path(directory)/'synthetic.aesgcm'
            process=subprocess.Popen(['docker','exec',name,'pg_dump','-U','postgres','-d','neondb',
                '--format=custom','--schema=sarsa_booking','--no-owner','--no-privileges'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
            with path.open('xb') as target:
                encrypt(process.stdout,target,key,{'project':'004-sarsa-jyotish-sansthan','format':'postgres-custom','day':'2026-09-29'})
            if process.wait(timeout=60):raise RuntimeError('Synthetic dump failed')
            result=restore_check(path,key)
            assert result['restored_migrations']==len(migrations)
            print('PASS: all',len(migrations),'migrations dumped, encrypted, authenticated and restored offline.')
    finally:
        subprocess.run(['docker','rm','-f','-v',name],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=30)

if __name__=='__main__':main()
