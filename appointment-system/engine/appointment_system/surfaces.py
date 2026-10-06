"""Complete booking route classification, separate from enquiries and paid-obligation work."""
import json
from pathlib import Path
from .configuration import installation

# The host router and application consume this same shipped policy.
_policy=json.loads((Path(__file__).resolve().parents[2]/"contracts/surfaces.json").read_text())
BOOKING_PREFIXES=tuple(_policy["booking_prefixes"])
PROTECTED_PREFIXES=tuple(_policy["protected_prefixes"])


def within(path,prefix):
    return path==prefix or path.startswith(prefix.rstrip("/")+"/")


def classify(path):
    if type(path) is not str or not path.startswith("/") or any(character in path for character in ("\\","%","?","#")) or any(ord(character)<32 or ord(character)==127 for character in path) or any(
            part in (".","..") for part in path.split("/")):
        return "invalid"
    # ASGI has already decoded the URL. Conservatively classify alternate case
    # and duplicate slashes even when the application itself would reject them.
    path="/"+"/".join(part for part in path.lower().split("/") if part)
    if path.endswith("/index.html"):path=path[:-11] or "/"
    elif path.endswith(".html"):path=path[:-5] or "/"
    # Private settlement, authenticated provider events and workers survive OFF.
    if path in _policy["protected_exact"] or any(within(path,prefix) for prefix in PROTECTED_PREFIXES):
        return "private"
    declared=installation()["surfaces"]
    if any(within(path,prefix) for prefix in BOOKING_PREFIXES):return "booking"
    exact=next((item["class"] for item in declared if item["path"].lower()==path),None)
    if exact is not None:return exact
    ancestors=[item for item in declared if item["path"]!="/" and within(path,item["path"].lower())]
    if ancestors:return max(ancestors,key=lambda item:len(item["path"]))["class"]
    return "general"
