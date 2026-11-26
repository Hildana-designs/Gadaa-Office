"""
Encrypted backups and restore.

A backup is one file: a zip (database snapshot + uploaded files + a short
manifest) encrypted with the backup key. A copy goes to the external drive
folder when one is set.
"""
import io
import json
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connection, connections
from django.utils import timezone

from core.crypto import decrypt_stream, encrypt_stream

FORMAT_VERSION = 1
SUFFIX = ".gadaabak"


def _is_sqlite():
    return settings.DATABASES["default"]["ENGINE"].endswith("sqlite3")


def _add_files(zf, root):
    root = Path(root)
    if not root.exists():
        return 0
    count = 0
    for path in sorted(root.rglob("*")):
        if path.is_file():
            zf.write(path, "files/" + path.relative_to(root).as_posix())
            count += 1
    return count


def make_backup(trigger="schedule", user=None):
    from core import audit
    from core.models import BackupRun

    run = BackupRun(status="failed", trigger=trigger)
    started = timezone.localtime()
    name = f"gadaa-backup-{started:%Y%m%d-%H%M%S}-{trigger}{SUFFIX}"
    if (Path(settings.BACKUP_DIR) / name).exists():
        name = f"gadaa-backup-{started:%Y%m%d-%H%M%S-%f}-{trigger}{SUFFIX}"
    try:
        if not settings.BACKUP_ENCRYPTION_KEY:
            raise RuntimeError("The backup key is missing from the settings file.")
        backup_dir = Path(settings.BACKUP_DIR)
        backup_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            zpath = tmp / "backup.zip"
            with zipfile.ZipFile(zpath, "w", compression=zipfile.ZIP_DEFLATED) as zf:
                if _is_sqlite():
                    snap = tmp / "db.sqlite3"
                    connection.ensure_connection()
                    dest = sqlite3.connect(snap)
                    with dest:
                        connection.connection.backup(dest)
                    dest.close()
                    zf.write(snap, "db.sqlite3")
                    db_kind = "sqlite"
                else:
                    buf = io.StringIO()
                    call_command("dumpdata", "--natural-foreign", "--natural-primary", "--exclude=contenttypes",
                                 "--exclude=auth.permission", "--exclude=sessions", stdout=buf)
                    zf.writestr("db.json", buf.getvalue())
                    db_kind = "json"
                n_files = _add_files(zf, settings.MEDIA_ROOT)
                zf.writestr("manifest.json", json.dumps({
                    "format": FORMAT_VERSION,
                    "created": started.isoformat(),
                    "database": db_kind,
                    "files": n_files,
                }, indent=2))
            target = backup_dir / name
            with open(zpath, "rb") as src, open(target, "wb") as dst:
                encrypt_stream(src, dst, settings.BACKUP_ENCRYPTION_KEY)
            # Prove the file can be read back before calling it a success.
            verify_backup(target)
        run.file_name = str(target)
        run.size_bytes = target.stat().st_size
        run.status = "ok"
        if settings.BACKUP_OFFSITE_DIR:
            off = Path(settings.BACKUP_OFFSITE_DIR)
            try:
                if not off.exists():
                    raise FileNotFoundError(f"{off} not found (is the external drive plugged in?)")
                shutil.copy2(target, off / name)
                run.offsite_copied = True
            except Exception as exc:  # backup itself is fine; warn about the copy
                run.message = f"Saved on this computer, but the external-drive copy failed: {exc}"
        if not run.message:
            run.message = "Saved and checked." + ("" if run.offsite_copied else " No external drive set.")
    except Exception as exc:
        run.status = "failed"
        run.message = str(exc)
    run.finished_at = timezone.now()
    run.save()
    audit.log("backup", run, note=f"{run.status}: {run.message}", user=user)
    return run


def _decrypt_to_zip(path, tmp):
    zpath = Path(tmp) / "restore.zip"
    with open(path, "rb") as src, open(zpath, "wb") as dst:
        decrypt_stream(src, dst, settings.BACKUP_ENCRYPTION_KEY)
    return zpath


def verify_backup(path):
    """Decrypt and check the backup without changing anything. Returns its manifest."""
    with tempfile.TemporaryDirectory() as tmp:
        zpath = _decrypt_to_zip(path, tmp)
        with zipfile.ZipFile(zpath) as zf:
            bad = zf.testzip()
            if bad:
                raise ValueError(f"Backup is damaged ({bad}).")
            manifest = json.loads(zf.read("manifest.json"))
            if manifest.get("format") != FORMAT_VERSION:
                raise ValueError("Backup was made by a different version of the app.")
            return manifest


def restore_backup(path, user=None, safety_copy=True):
    """
    Replace the current database and files with the backup's contents.
    A safety backup of the current state is made first.
    """
    from core import audit

    path = Path(path)
    manifest = verify_backup(path)
    if safety_copy:
        safety = make_backup(trigger="pre-restore", user=user)
        if safety.status != "ok":
            raise RuntimeError(f"Could not make a safety copy first, so nothing was changed: {safety.message}")
    with tempfile.TemporaryDirectory() as tmp:
        zpath = _decrypt_to_zip(path, tmp)
        extract = Path(tmp) / "x"
        with zipfile.ZipFile(zpath) as zf:
            zf.extractall(extract)
        if manifest["database"] == "sqlite":
            if not _is_sqlite():
                raise RuntimeError("This backup holds a SQLite database; use the PostgreSQL move script instead.")
            # Copy page by page into the live database (works while the file is open).
            connection.ensure_connection()
            src = sqlite3.connect(extract / "db.sqlite3")
            src.backup(connection.connection)
            src.close()
        else:
            call_command("flush", "--no-input")
            call_command("loaddata", str(extract / "db.json"))
        media = Path(settings.MEDIA_ROOT)
        if media.exists():
            shutil.rmtree(media)
        media.mkdir(parents=True, exist_ok=True)
        files_dir = extract / "files"
        if files_dir.exists():
            shutil.copytree(files_dir, media, dirs_exist_ok=True)
    connections.close_all()
    if safety_copy:
        # The restored database does not know about the safety copy; record it again.
        from core.models import BackupRun

        BackupRun.objects.create(status="ok", trigger="pre-restore", file_name=safety.file_name,
                                 size_bytes=safety.size_bytes, offsite_copied=safety.offsite_copied,
                                 finished_at=timezone.now(),
                                 message="Safety copy of the data as it was just before a restore.")
    audit.log("restore", note=f"Restored from {path.name} (made {manifest['created']})", user=user)
    return manifest
