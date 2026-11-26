"""
Background worker: one simple loop, no message broker.
Phase 0 job: the daily backup. Later phases add mail polling and reminders.
"""
import time

from django.conf import settings
from django.core.management import BaseCommand
from django.utils import timezone

from core.backup import make_backup
from core.models import BackupRun


def backup_due(now=None):
    now = timezone.localtime(now)
    if now.hour < settings.BACKUP_HOUR:
        return False
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return not BackupRun.objects.filter(status="ok", trigger="schedule", started_at__gte=start_of_day).exists()


def failed_recently(now=None):
    """After a failure, wait an hour before trying again."""
    now = timezone.now() if now is None else now
    last = BackupRun.objects.filter(trigger="schedule").first()
    return bool(last and last.status == "failed" and (now - last.started_at).total_seconds() < 3600)


class Command(BaseCommand):
    help = "Run background jobs (daily backup). Started by the start script."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Run due jobs once and stop.")

    def handle(self, *args, once=False, **options):
        heartbeat = settings.DATA_DIR / "logs" / "worker-heartbeat.txt"
        heartbeat.parent.mkdir(parents=True, exist_ok=True)
        self.stdout.write("GADAA worker started.")
        while True:
            try:
                if backup_due() and not failed_recently():
                    run = make_backup(trigger="schedule")
                    self.stdout.write(f"{timezone.localtime():%Y-%m-%d %H:%M} backup {run.status}: {run.message}")
                heartbeat.write_text(timezone.localtime().isoformat(), encoding="utf-8")
            except Exception as exc:  # never let the loop die
                self.stderr.write(f"Worker error: {exc}")
            if once:
                return
            time.sleep(60)
