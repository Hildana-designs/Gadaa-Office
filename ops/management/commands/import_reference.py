"""
Import the reference files. Runs as a trial by default (nothing saved) and
writes a report. Add --apply to save.

    python manage.py import_reference --source "C:\\GADAA\\reference"
    python manage.py import_reference --source "C:\\GADAA\\reference" --apply
"""
from pathlib import Path

from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core import audit
from ops.importer import trips, workbook
from ops.importer.base import Report

FILES = {
    "workbook": "01_GADAA_Operations_Workbook.xlsx",
    "trip005": "trip-files/GAD-TOUR-005_management_cost_analysis.xlsx",
    "surma": "trip-files/GAD-TOUR-001_Surma_expense_analysis.xlsx",
    "bookings": "trip-files/Hotel_bookings_Nov2026.xlsx",
}


class Rollback(Exception):
    pass


def run_all(source, report):
    workbook.run(source / FILES["workbook"], report)
    trips.import_hotel_contacts(source / FILES["bookings"], report)
    trips.import_trip005(source / FILES["trip005"], report)
    trips.import_surma(source / FILES["surma"], report)
    trips.import_bookings(source / FILES["bookings"], report)


class Command(BaseCommand):
    help = "Import the workbook and trip files (trial run unless --apply)."

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, help="Folder holding the reference files.")
        parser.add_argument("--apply", action="store_true", help="Save the import. Without it nothing is saved.")
        parser.add_argument("--report", help="Where to write the report (default: data/logs).")

    def handle(self, source, apply, report=None, **options):
        source = Path(source)
        missing = [name for name in FILES.values() if not (source / name).exists()]
        if missing:
            raise CommandError("Missing files: " + ", ".join(missing))
        rep = Report()
        try:
            with transaction.atomic():
                run_all(source, rep)
                if not apply:
                    raise Rollback
                if not rep.all_checks_pass:
                    raise CommandError("Totals do not match, so nothing was saved. See the report.")
                audit.log("import", note=f"Reference import applied: {rep.created} created, {rep.updated} updated, "
                                         f"{len(rep.rejected)} rejected, {len(rep.doubtful)} doubtful")
        except Rollback:
            pass
        except CommandError:
            self._write(rep, apply, report)
            raise
        path = self._write(rep, apply, report)
        style = self.style.SUCCESS if rep.all_checks_pass else self.style.ERROR
        self.stdout.write(style(f"{'Applied' if apply else 'Trial run'}: {rep.created} created, {rep.updated} updated, "
                                f"{rep.unchanged} unchanged, {len(rep.rejected)} rejected, {len(rep.doubtful)} doubtful. "
                                f"Totals {'all match' if rep.all_checks_pass else 'DO NOT MATCH'}."))
        self.stdout.write(f"Report: {path}")

    def _write(self, rep, apply, target):
        logs = Path(target) if target else settings.DATA_DIR / "logs" / f"import-report-{timezone.localtime():%Y%m%d-%H%M%S}.md"
        logs.parent.mkdir(parents=True, exist_ok=True)
        logs.write_text(rep.as_markdown("Reference import report", applied=apply), encoding="utf-8")
        return logs
