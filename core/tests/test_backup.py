import io
import shutil
import tempfile
from datetime import datetime, timezone as dt_tz
from pathlib import Path
from unittest import mock

from cryptography.fernet import Fernet
from django.conf import settings
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings

from core.backup import make_backup, restore_backup, verify_backup
from core.crypto import decrypt_stream, encrypt_stream
from core.models import BackupRun
from ops.models import Passenger, Trip


class StreamEncryption(TransactionTestCase):
    def test_round_trip_large_data(self):
        key = Fernet.generate_key().decode()
        data = b"x" * (9 * 1024 * 1024 + 17)  # bigger than one chunk
        enc, out = io.BytesIO(), io.BytesIO()
        encrypt_stream(io.BytesIO(data), enc, key)
        self.assertNotIn(b"xxxxxxxx", enc.getvalue()[:100])
        enc.seek(0)
        decrypt_stream(enc, out, key)
        self.assertEqual(out.getvalue(), data)

    def test_wrong_key_is_refused(self):
        enc = io.BytesIO()
        encrypt_stream(io.BytesIO(b"secret"), enc, Fernet.generate_key().decode())
        enc.seek(0)
        with self.assertRaises(ValueError):
            decrypt_stream(enc, io.BytesIO(), Fernet.generate_key().decode())


class BackupAndRestore(TransactionTestCase):
    """The Phase 0 'done when': a restore from backup has been tested."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.db = self.tmp / "db.sqlite3"
        self.override = override_settings(BACKUP_DIR=self.tmp / "backups", BACKUP_OFFSITE_DIR=str(self.tmp / "usb"),
                                          MEDIA_ROOT=self.tmp / "files")
        self.override.enable()
        (self.tmp / "usb").mkdir()
        (self.tmp / "files" / "receipts").mkdir(parents=True)
        (self.tmp / "files" / "receipts" / "r1.txt").write_text("receipt one", encoding="utf-8")

    def tearDown(self):
        self.override.disable()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_backup_is_encrypted_checked_and_copied(self):
        Trip.objects.create(name="Before backup")
        run = make_backup(trigger="manual")
        self.assertEqual(run.status, "ok", run.message)
        self.assertTrue(run.offsite_copied)
        path = Path(run.file_name)
        self.assertTrue((self.tmp / "usb" / path.name).exists())
        self.assertNotIn(b"Before backup", path.read_bytes())
        self.assertEqual(verify_backup(path)["files"], 1)

    def test_restore_brings_back_data_and_files(self):
        trip = Trip.objects.create(name="Original name")
        Passenger.objects.create(trip=trip, full_name="Made UP", passport_no="P123")
        run = make_backup(trigger="manual")
        self.assertEqual(run.status, "ok", run.message)
        # Things go wrong after the backup
        Trip.objects.update(name="Damaged")
        Trip.objects.create(name="Added later")
        (self.tmp / "files" / "receipts" / "r1.txt").unlink()
        restore_backup(run.file_name)
        names = sorted(Trip.objects.values_list("name", flat=True))
        self.assertEqual(names, ["Original name"])
        self.assertEqual(Passenger.objects.get().passport_no, "P123")
        self.assertEqual((self.tmp / "files" / "receipts" / "r1.txt").read_text(encoding="utf-8"), "receipt one")
        # A safety copy was made before restoring
        self.assertTrue(BackupRun.objects.filter(trigger="pre-restore", status="ok").exists())

    def test_missing_key_fails_loudly(self):
        with override_settings(BACKUP_ENCRYPTION_KEY=""):
            run = make_backup()
        self.assertEqual(run.status, "failed")
        from core.context_processors import backup_warning

        self.assertIn("failed", backup_warning())

    def test_missing_external_drive_is_a_warning_not_a_failure(self):
        with override_settings(BACKUP_OFFSITE_DIR=str(self.tmp / "not-plugged-in")):
            run = make_backup()
        self.assertEqual(run.status, "ok")
        self.assertFalse(run.offsite_copied)
        self.assertIn("external", run.message)

    def test_worker_runs_daily_backup_once(self):
        from core.management.commands import worker

        evening = datetime(2026, 11, 26, 17, 0, tzinfo=dt_tz.utc)  # 20:00 in Addis
        with mock.patch("django.utils.timezone.now", return_value=evening):
            self.assertTrue(worker.backup_due())
            call_command("worker", "--once", stdout=io.StringIO())
            self.assertFalse(worker.backup_due())
        self.assertEqual(BackupRun.objects.filter(trigger="schedule", status="ok").count(), 1)
        morning = datetime(2026, 11, 27, 5, 0, tzinfo=dt_tz.utc)  # 08:00 next day, before backup hour
        with mock.patch("django.utils.timezone.now", return_value=morning):
            self.assertFalse(worker.backup_due())
