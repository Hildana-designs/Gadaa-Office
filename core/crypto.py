"""
Encryption helpers.

* EncryptedTextField stores passport and ID numbers encrypted in the database.
  The key comes from GADAA_FIELD_KEY in the settings file, never from code.
* Stream helpers encrypt backup files in chunks so large file folders do not
  have to fit in memory.
"""
import struct

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models

PREFIX = "enc1:"


def _fernet(key):
    if not key:
        raise ImproperlyConfigured("Encryption key is missing from the settings file.")
    return Fernet(key.encode() if isinstance(key, str) else key)


def field_cipher():
    return _fernet(settings.FIELD_ENCRYPTION_KEY)


def encrypt_text(value):
    if value in (None, ""):
        return value
    return PREFIX + field_cipher().encrypt(str(value).encode("utf-8")).decode("ascii")


def decrypt_text(value):
    if value in (None, "") or not str(value).startswith(PREFIX):
        return value
    try:
        return field_cipher().decrypt(value[len(PREFIX):].encode("ascii")).decode("utf-8")
    except InvalidToken as exc:
        raise ImproperlyConfigured(
            "Cannot read an encrypted value: the field key in the settings file does not match."
        ) from exc


class EncryptedTextField(models.TextField):
    """Text stored encrypted. Reading it in Python returns the plain value."""

    description = "Encrypted text"

    def from_db_value(self, value, expression, connection):
        return decrypt_text(value)

    def to_python(self, value):
        return decrypt_text(value) if isinstance(value, str) else value

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value in (None, "") or str(value).startswith(PREFIX):
            return value
        return encrypt_text(value)


# ---- backup stream encryption -------------------------------------------
MAGIC = b"GADAABK1"
CHUNK = 4 * 1024 * 1024


def encrypt_stream(src, dst, key):
    f = _fernet(key)
    dst.write(MAGIC)
    while True:
        block = src.read(CHUNK)
        if not block:
            break
        token = f.encrypt(block)
        dst.write(struct.pack(">I", len(token)))
        dst.write(token)


def decrypt_stream(src, dst, key):
    f = _fernet(key)
    if src.read(len(MAGIC)) != MAGIC:
        raise ValueError("This is not a GADAA backup file.")
    while True:
        header = src.read(4)
        if not header:
            break
        (length,) = struct.unpack(">I", header)
        token = src.read(length)
        try:
            dst.write(f.decrypt(token))
        except InvalidToken as exc:
            raise ValueError("Wrong backup key, or the backup file is damaged.") from exc
