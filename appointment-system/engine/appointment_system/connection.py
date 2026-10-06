"""Match every protected connection against independently declared project facts."""
import os
import psycopg
from psycopg.conninfo import conninfo_to_dict
from .configuration import installation
from .errors import Rejected


class StorageUnavailable(Exception):
    pass


def checked_config(dsn,expected_host,*,purpose="web"):
    try:
        facts=installation()
        target=facts["database_targets"][purpose]
        config=conninfo_to_dict(dsn) if dsn else {}
        allowed={"host","port","dbname","user","password","sslmode","sslrootcert","channel_binding"}
        if (expected_host!=target["host"] or config.get("host")!=target["host"]
            or config.get("dbname")!=target["database"] or config.get("user")!=target["role"]
            or config.get("port","5432")!=str(target["port"]) or set(config)-allowed
            or not config.get("password") or config.get("sslmode") not in ("require","verify-full")
            or config.get("channel_binding","prefer") not in ("prefer","require")
            or any(os.environ.get(name) for name in ("PGOPTIONS","PGSERVICE","PGSERVICEFILE","PGHOST","PGHOSTADDR"))
            or "-pooler" in target["host"] and target["pooling"] is not True
            or purpose in ("backup","migration","maintenance") and target["pooling"] is not False):
            raise ValueError()
        return config
    except (psycopg.Error,ValueError,KeyError,Rejected):
        raise StorageUnavailable("This operation requires its declared protected database connection.") from None
