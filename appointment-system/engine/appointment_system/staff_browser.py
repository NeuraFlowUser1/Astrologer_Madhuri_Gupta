"""Public, installation-bound recovery journals, independent of Google setup."""
import json
from pathlib import Path
import re

from fastapi.responses import Response

from .connection import StorageUnavailable
from .serialization import decode

PURPOSES = ('client', 'company', 'calendar', 'inbox', 'enquiry')


def configuration(ring, directory=None):
    directory = directory or Path(__file__).parents[2].parent / 'appointment-settings'
    path = directory / 'staff-browser.json'
    result = {'version': 1, 'installation_id': ring.installation_id,
              'environment': ring.environment, 'legacy': {name: [] for name in PURPOSES}}
    if not path.exists() and not path.is_symlink():
        return result
    try:
        if (any(part.is_symlink() for part in (path, *path.parents))
                or not path.is_file() or path.stat().st_size > 8192):
            raise ValueError()
        value = decode(path.read_bytes())
        if (set(value) != set(result) or type(value['version']) is not int or value['version'] != 1
                or value['installation_id'] != ring.installation_id
                or value['environment'] != ring.environment or type(value['legacy']) is not dict
                or set(value['legacy']) != set(PURPOSES)):
            raise ValueError()
        seen = set()
        for keys in value['legacy'].values():
            if type(keys) is not list or len(keys) > 4:
                raise ValueError()
            for key in keys:
                if (type(key) is not str or not re.fullmatch(r'[a-z0-9:-]{1,150}', key)
                        or key.startswith('appointment-system:') or key in seen):
                    raise ValueError()
                seen.add(key)
        return value
    except Exception:
        raise StorageUnavailable('Saved staff actions cannot be configured.') from None


def script(ring):
    data = json.dumps(configuration(ring), separators=(',', ':'), ensure_ascii=True)
    source = (Path(__file__).parent / 'studio_assets/staff-actions.js').read_text()
    return Response(source.replace('/*STAFF_BROWSER_CONFIGURATION*/null', data),
                    media_type='text/javascript', headers={'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex'})


def add_routes(app, ring):
    @app.get('/api/enquiry-studio/staff-actions.js', include_in_schema=False)
    @app.get('/api/company/staff-actions.js', include_in_schema=False)
    @app.get('/api/studio/staff-actions.js', include_in_schema=False)
    def journal_script():
        return script(ring)
