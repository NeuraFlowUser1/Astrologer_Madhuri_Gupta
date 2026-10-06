"""Project-contained appointment application; no account work runs on import."""
import os
import sys
from pathlib import Path

entry = Path(__file__).absolute()
if any(path.is_symlink() for path in (entry, *entry.parents)):
    raise RuntimeError("Project entry point links are forbidden.")
project = entry.parents[1]
package = project / "appointment-system"
sys.path[:0] = [str(package), str(package / "engine")]
from appointment_system.runtime import create_application

app = create_application(project / "appointment-settings/project.json", dict(os.environ))
