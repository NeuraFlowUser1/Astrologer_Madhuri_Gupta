"""Owned, disconnected PostgreSQL proof targets. Never reads a customer DSN."""
from pathlib import Path
from contextlib import contextmanager
import hashlib
import fcntl
import atexit
import json
import os
import re
import subprocess
import time
import tempfile

IMAGES = {
    "abs-implementation-pg16": "postgres@sha256:efedf3595f1d6f415c08568ba171029bf54052e754cc9f030e3f2412b21f3d67",
    "abs-implementation-pg18": "postgres@sha256:d3e1620b530c944afa6e887d22eb899824da68e19c52024bf98f5220c88a65b2",
}
LABEL = "abs-isolated-implementation"
ROOT = Path(__file__).resolve().parents[2]
_PROOF_LOCKS={}

def _release_proof_locks():
    for handle in _PROOF_LOCKS.values():handle.close()
    _PROOF_LOCKS.clear()

atexit.register(_release_proof_locks)


@contextmanager
def delegated_proof(name):
    """Let one awaited child process own the fixture, then restore our turn.

    Used only when the parent performs no SQL until the child exits. Without
    this handoff a full test run can hold the lock its own child needs.
    """
    if name not in IMAGES:
        raise ValueError('Only a declared isolated proof may be delegated.')
    previous=_PROOF_LOCKS.pop(name,None)
    if previous is not None:previous.close()
    try:yield
    finally:
        if previous is not None:SQLTarget(name)


def command(arguments, *, body=None):
    return subprocess.run(["docker", *arguments], input=body, capture_output=True,
                          text=True, timeout=45)


class SQLTarget:
    def __init__(self, name):
        if name not in IMAGES:
            raise ValueError("Only the two declared isolated targets may be used.")
        self.name = name
        if name not in _PROOF_LOCKS:
            handle=open('/tmp/'+name+'-proof.lock','a')
            fcntl.flock(handle.fileno(),fcntl.LOCK_EX)
            _PROOF_LOCKS[name]=handle

    def check_owned(self):
        result = command(["inspect", "--format", "{{index .Config.Labels \"neuraflow-purpose\"}}", self.name])
        if result.returncode or result.stdout.strip() != LABEL:
            raise ValueError("The target is not an owned test container.")
        detail = command(["inspect", "--format", "{{.HostConfig.NetworkMode}}|{{json .HostConfig.PortBindings}}", self.name])
        if detail.stdout.strip() not in ("none|null", "none|{}"):
            raise ValueError("The target must have no network or published ports.")

    def start(self, *, reset=False,native_socket=False):
        existing = command(["inspect", self.name])
        if not existing.returncode:
            self.check_owned()
            if reset:
                removed = command(["rm", "-f", self.name])
                if removed.returncode:
                    raise RuntimeError("Could not reset the owned test container.")
            else:
                # A power interruption can leave a valid owned container stopped.
                # Restart only after checking its purpose and disconnected network.
                started = command(["start", self.name])
                if started.returncode:
                    raise RuntimeError("Could not restart the owned test container.")
        if existing.returncode or reset:
            arguments=["run", "-d", "--name", self.name, "--network", "none",
                               "--label", "neuraflow-purpose="+LABEL,
                               "--tmpfs", "/var/lib/postgresql", "--tmpfs", "/tmp",
                               "-e", "POSTGRES_HOST_AUTH_METHOD=trust"]
            if native_socket:
                # Synthetic native psycopg proof only. No TCP port, customer
                # password or network is exposed. The directory is newly owned.
                socket=Path(tempfile.mkdtemp(prefix='abs-native-socket-'))
                socket.chmod(0o777)
                (socket/'proof-target').write_text(LABEL+'\n'+self.name+'\n')
                arguments+=['--mount','type=bind,src='+str(socket)+',dst=/var/run/postgresql']
            created = command(arguments+[IMAGES[self.name]])
            if created.returncode:
                raise RuntimeError("Could not start the owned test container.")
        for _ in range(60):
            ready = command(["exec", "--user", "postgres", self.name, "pg_isready"])
            if not ready.returncode:
                self.check_owned()
                return
            time.sleep(.25)
        raise RuntimeError("The isolated database did not become ready.")

    def native_socket(self):
        self.check_owned()
        mounts=json.loads(command(['inspect','--format','{{json .Mounts}}',self.name]).stdout)
        candidates=[Path(m['Source']) for m in mounts if m.get('Type')=='bind' and m.get('Destination')=='/var/run/postgresql']
        if len(candidates)!=1:raise ValueError('Declared native proof socket is missing.')
        path=candidates[0]
        if (path.is_symlink() or path.parent!=Path('/tmp') or not path.name.startswith('abs-native-socket-')
            or (path/'proof-target').read_text()!=LABEL+'\n'+self.name+'\n'):
            raise ValueError('Native proof socket is not owned.')
        return str(path)

    def sql(self, statement, *, role="postgres", check=True):
        if role not in ("postgres", "appointment_system_web", "abs_staff", "abs_worker",
                        "abs_company", "abs_backup", "abs_maintenance", "abs_journal"):
            raise ValueError("Unknown isolated role.")
        result = command(["exec", "-i", "--user", "postgres", self.name,
                          "psql", "-X", "-U", role, "-d", "postgres",
                          "-v", "ON_ERROR_STOP=1", "-Atq"], body=statement)
        if result.returncode and check:
            raise AssertionError("Isolated SQL failed: " + result.stderr[:1400])
        return result

    def scalar(self, statement, *, role="postgres"):
        return self.sql(statement, role=role).stdout.strip()

    def value(self, statement, *, role="postgres"):
        value=self.scalar(statement, role=role)
        return None if value=='' else json.loads(value)

    def migrate(self):
        self.check_owned()
        paths = sorted((ROOT/"engine/appointment_system/migrations").glob("[0-9][0-9][0-9]_*.sql"))
        existing={}
        if self.scalar("SELECT to_regclass('appointment_system.schema_migrations') IS NOT NULL;")=='t':
            existing=self.value("SELECT coalesce(jsonb_object_agg(version,sha256),'{}'::jsonb) FROM appointment_system.schema_migrations;")
        known={path.name for path in paths}
        if set(existing)-known:raise AssertionError('The isolated target has unknown migrations; rebuild it explicitly.')
        for path in paths:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            if path.name in existing:
                if existing[path.name]!=digest:
                    raise AssertionError('Applied migration changed: '+path.name+'; rebuild the isolated target explicitly.')
                continue
            self.sql("BEGIN;\n"+path.read_text()+"\nINSERT INTO appointment_system.schema_migrations"
                     "(version,sha256) VALUES ('"+path.name+"','"+digest+"');\nCOMMIT;")
        return len(paths)


def literal(value):
    if value is None:return 'NULL'
    if type(value) is bool:return 'true' if value else 'false'
    if type(value) is int and -9223372036854775808<=value<=9223372036854775807:return str(value)
    if type(value) in (dict, list):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if type(value) is not str:
        raise ValueError("Test literals must be text, JSON, a bounded integer, boolean or null.")
    return "'" + value.replace("'", "''") + "'"


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("target", choices=IMAGES)
    parser.add_argument("--reset", action="store_true")
    parser.add_argument("--native-socket",action="store_true")
    arguments = parser.parse_args()
    target = SQLTarget(arguments.target)
    target.start(reset=arguments.reset,native_socket=arguments.native_socket)
    count = target.migrate()
    print(json.dumps({"target":target.name,"migrations":count,"network":"none","status":"ready"}))
