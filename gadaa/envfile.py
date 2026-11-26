"""Small helpers to read the settings file and the database address."""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse


def load_env_file(path):
    """Read KEY=VALUE lines into os.environ without overriding real variables."""
    path = Path(path)
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def parse_database_url(url, default_sqlite):
    """Turn 'postgres://user:pass@host:5432/name' or 'sqlite:///path' into Django settings."""
    if not url:
        return {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": str(default_sqlite),
            "OPTIONS": {"timeout": 20},
        }
    parsed = urlparse(url)
    if parsed.scheme in {"postgres", "postgresql"}:
        return {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": unquote(parsed.path.lstrip("/")),
            "USER": unquote(parsed.username or ""),
            "PASSWORD": unquote(parsed.password or ""),
            "HOST": parsed.hostname or "localhost",
            "PORT": str(parsed.port or 5432),
        }
    if parsed.scheme == "sqlite":
        name = url[len("sqlite:///"):] if url.startswith("sqlite:///") else parsed.path
        return {"ENGINE": "django.db.backends.sqlite3", "NAME": name, "OPTIONS": {"timeout": 20}}
    raise ValueError(f"Unsupported database address: {parsed.scheme}")
