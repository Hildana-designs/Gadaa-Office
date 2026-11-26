from django.core.management import BaseCommand, CommandError

from core.backup import make_backup


class Command(BaseCommand):
    help = "Make an encrypted backup now."

    def handle(self, *args, **options):
        run = make_backup(trigger="manual")
        if run.status != "ok":
            raise CommandError(f"Backup failed: {run.message}")
        self.stdout.write(self.style.SUCCESS(f"Backup saved: {run.file_name}\n{run.message}"))
