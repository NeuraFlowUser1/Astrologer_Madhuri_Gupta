"""Read-only package/import proof: no credentials, outbound calls or stored data."""
import importlib.util
import json
import os
from pathlib import Path
import socket
import sys

root = Path(__file__).absolute().parents[3]
package = root / "appointment-system"
sys.path[:0] = [str(package), str(package / "engine")]
from tools.install.package import verify

expected = "97ab5d49fc559eb1acdeb7157d4561134d1bad824cca298506f48b2a9d32b49d"
release = verify(package)
assert release["content_digest"] == expected
assert len(release["files"]) == 573
migrations = sorted((package / "engine/appointment_system/migrations").glob("*.sql"))
assert len(migrations) == 36

def refuse_connection(*_args, **_kwargs):
    raise AssertionError("Outbound connections are forbidden in this import proof")

socket.socket.connect = refuse_connection
socket.socket.connect_ex = refuse_connection
socket.create_connection = refuse_connection
# Do not inherit private machine settings into this deliberately unconfigured proof.
os.environ.clear()
spec = importlib.util.spec_from_file_location("sarsa_release_entry", root / "api/index.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
from fastapi.testclient import TestClient
with TestClient(entry.app, base_url="https://www.sarsajyotishsansthan.com") as client:
    response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["code"] == "temporarily_unavailable"
    assert client.get("/api/health", headers={"host": "untrusted.example"}).status_code == 421
print(json.dumps({"package_digest": expected, "manifest_files": 573, "migrations": len(migrations),
                  "entry_import": "passed", "health_without_private_configuration": response.status_code,
                  "untrusted_host_rejected": 421, "outbound_connections": "forbidden", "provider_acceptance": "not exercised"}))
