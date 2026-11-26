from django.core.management import BaseCommand, CommandError

from core.backup import restore_backup, verify_backup


class Command(BaseCommand):
    help = "Restore a backup file. Stop the app first. A safety backup is made before anything changes."

    def add_arguments(self, parser):
        parser.add_argument("backup_file")
        parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation.")
        parser.add_argument("--check-only", action="store_true", help="Only check the file can be read.")

    def handle(self, backup_file, yes, check_only, **options):
        try:
            manifest = verify_backup(backup_file)
        except Exception as exc:
            raise CommandError(f"Cannot use this backup: {exc}")
        self.stdout.write(f"Backup made {manifest['created']}, {manifest['files']} files. It is readable.")
        if check_only:
            return
        if not yes:
            answer = input("This replaces ALL current data with the backup. Type RESTORE to continue: ")
            if answer.strip() != "RESTORE":
                raise CommandError("Stopped. Nothing was changed.")
        restore_backup(backup_file)
        self.stdout.write(self.style.SUCCESS("Restore finished. Start the app again."))
