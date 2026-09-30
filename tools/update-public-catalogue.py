"""Run from the client root after changing the approved booking policy."""
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backend.booking_engine.policy import policy_snapshot, policy_version
(ROOT/'frontend/src/site/catalogue.json').write_text(json.dumps({'quote_version':policy_version(),'services':policy_snapshot()['services']},indent=2)+'\n')
print('Public service catalogue updated from the booking policy.')
