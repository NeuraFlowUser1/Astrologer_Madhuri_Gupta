"""One-command Chrome proof; the fixture owns its exact temporary resources."""
import argparse
import json
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT/'tools/verification/artifacts'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--node', required=True)
    args = parser.parse_args()
    with tempfile.TemporaryFile() as log:
        fixture = subprocess.Popen([sys.executable, str(ROOT/'tools/verification/chrome_fixture.py')],
                                   cwd=ROOT, stdout=log, stderr=log)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                log.seek(0)
                if b'Chrome fixture ready.' in log.read():
                    break
                if fixture.poll() is not None:
                    raise RuntimeError('The isolated Chrome fixture failed during setup.')
                time.sleep(.1)
            else:
                raise RuntimeError('The isolated Chrome fixture did not become ready.')
            subprocess.run([args.node, str(ROOT/'tools/verification/chrome_run.mjs')],
                           cwd=ROOT, check=True, timeout=180)
            if fixture.wait(timeout=45) != 0:
                raise RuntimeError('Chrome assertions did not match the saved database.')
            print('PASS: isolated Chrome and committed database proof.')
        finally:
            if fixture.poll() is None:
                path = ARTIFACTS/'chrome-fixture.json'
                if path.is_file():
                    identity = json.loads(path.read_text())['id']
                    (ARTIFACTS/'chrome-completed.json').write_text(json.dumps({'id': identity, 'passed': False}))
                try:
                    fixture.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    # Only the subprocess started above; never any other project.
                    fixture.send_signal(signal.SIGINT)
                    fixture.wait(timeout=15)


if __name__ == '__main__':
    main()
