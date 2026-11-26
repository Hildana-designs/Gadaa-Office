"""
First-time setup, run before Django starts: creates the data folder and a
settings file with fresh keys. Safe to run again: an existing file is kept.

    python -m gadaa.bootstrap
"""
import os
import secrets
import socket
from pathlib import Path

from cryptography.fernet import Fernet

BASE_DIR = Path(__file__).resolve().parent.parent


def _template():
    host = socket.gethostname()
    return f"""# GADAA settings file. Keep it private. Never put it in Git or email it.
# The three keys below are needed to read passport numbers and to restore
# backups. Print this file or copy it to a USB stick kept in a safe place.
GADAA_SECRET_KEY={secrets.token_urlsafe(50)}
GADAA_FIELD_KEY={Fernet.generate_key().decode()}
GADAA_BACKUP_KEY={Fernet.generate_key().decode()}

# Addresses people type in the browser, separated by commas.
GADAA_ALLOWED_HOSTS=localhost,127.0.0.1,{host},{host.lower()}
GADAA_CSRF_ORIGINS=https://localhost:8443,https://{host}:8443,https://{host.lower()}:8443
GADAA_PORT=8443
GADAA_HTTPS=true
GADAA_MFA_REQUIRED=true
GADAA_SESSION_MINUTES=30

# Backups: daily at this hour. Set the second folder to your external drive, e.g. E:\\GADAA-backups
GADAA_BACKUP_HOUR=19
GADAA_BACKUP_OFFSITE_DIR=

# Leave empty for the office database (SQLite). Example for a server later:
# GADAA_DATABASE_URL=postgres://gadaa:password@localhost:5432/gadaa
GADAA_DATABASE_URL=
"""



def main():
    data = Path(os.environ.get("GADAA_DATA_DIR", BASE_DIR / "data")).resolve()
    env_file = Path(os.environ.get("GADAA_ENV_FILE", data / "gadaa.env"))
    data.mkdir(parents=True, exist_ok=True)
    for sub in ("files", "backups", "certs", "logs"):
        (data / sub).mkdir(exist_ok=True)
    if env_file.exists():
        print(f"Settings file already exists: {env_file}")
        return
    env_file.write_text(_template(), encoding="utf-8")
    print(f"Created {env_file}.")
    print("IMPORTANT: it holds new keys. Keep a copy somewhere safe (see README, 'Keys').")


if __name__ == "__main__":
    main()
