"""Settings for automated tests: throwaway keys and folders, made-up data only."""
import os
import tempfile

from cryptography.fernet import Fernet

_tmp = tempfile.mkdtemp(prefix="gadaa-test-")
os.environ["GADAA_DATA_DIR"] = _tmp
os.environ["GADAA_ENV_FILE"] = os.path.join(_tmp, "none.env")
os.environ.setdefault("GADAA_SECRET_KEY", "test-only-secret")
os.environ.setdefault("GADAA_FIELD_KEY", Fernet.generate_key().decode())
os.environ.setdefault("GADAA_BACKUP_KEY", Fernet.generate_key().decode())
os.environ.setdefault("GADAA_HTTPS", "false")
os.environ.setdefault("GADAA_ALLOWED_HOSTS", "testserver,localhost")

from gadaa.settings import *  # noqa: E402,F401,F403

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
STORAGES["staticfiles"] = {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"}  # noqa: F405
