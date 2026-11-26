"""
Import tests against the real reference files. The files hold client names
and bank details, so they are not in Git: point GADAA_REFERENCE_DIR at the
folder to run these tests (they are skipped otherwise).
"""
import io
import os
from decimal import Decimal
from pathlib import Path
from unittest import skipUnless

from django.core.management import call_command
from django.test import TestCase

from core.models import AppSetting, ImportRecord
from ops.models import CostLine, Expense, FeeReference, HotelBooking, Supplier, Task, Trip

REF = Path(os.environ.get("GADAA_REFERENCE_DIR", "/mnt/project-files/reference"))
HAVE_FILES = (REF / "01_GADAA_Operations_Workbook.xlsx").exists()


@skipUnless(HAVE_FILES, "reference files not available")
class ReferenceImport(TestCase):
    def run_import(self, apply=True):
        out = io.StringIO()
        args = ["import_reference", "--source", str(REF), "--report", os.devnull]
        if apply:
            args.append("--apply")
        call_command(*args, stdout=out)
        return out.getvalue()

    def test_trial_run_saves_nothing(self):
        self.run_import(apply=False)
        self.assertEqual(Trip.objects.count(), 0)
        self.assertEqual(ImportRecord.objects.count(), 0)

    def test_totals_match_to_the_cent(self):
        self.run_import()
        t5 = Trip.objects.get(code="GAD-TOUR-005")
        self.assertEqual(t5.price_etb, Decimal("1043946.90"))
        self.assertEqual(t5.cost_total_etb(), Decimal("614508.92"))
        self.assertEqual(t5.profit_etb(), Decimal("429437.98"))
        self.assertEqual(t5.days, 15)
        self.assertEqual(t5.pax, 2)
        surma = Trip.objects.get(code="GAD-TOUR-001")
        self.assertEqual(surma.cost_total_etb(), Decimal("498473.78"))
        self.assertEqual(surma.net_cost_etb(), Decimal("496313.78"))
        self.assertFalse(surma.fx_confirmed)

    def test_category_totals_match_the_manager_sheet(self):
        self.run_import()
        t5 = Trip.objects.get(code="GAD-TOUR-005")
        expected = {"Hotels (lodging)": "166770.61", "Driver": "112500.00", "Guide daily fee": "82500.00",
                    "Fuel": "53238.31", "Client meals": "65400.00", "Entrances and village fees": "58500.00",
                    "Local guides": "21800.00", "Boats and vehicle fees": "9700.00", "Guide and crew meals": "30000.00",
                    "Guide hotel rooms": "13000.00", "Bottled water": "1100.00"}
        for cat, amount in expected.items():
            got = sum(l.amount_etb for l in t5.cost_lines.filter(category=cat))
            self.assertEqual(got, Decimal(amount), cat)

    def test_running_twice_creates_no_duplicates(self):
        self.run_import()
        counts = {m.__name__: m.objects.count() for m in (Trip, CostLine, HotelBooking, Expense, Supplier, FeeReference, Task, AppSetting)}
        out = self.run_import()
        self.assertIn("0 created, 0 updated", out)
        again = {m.__name__: m.objects.count() for m in (Trip, CostLine, HotelBooking, Expense, Supplier, FeeReference, Task, AppSetting)}
        self.assertEqual(counts, again)

    def test_doubtful_values_are_flagged_not_guessed(self):
        self.run_import()
        self.assertFalse(AppSetting.objects.get(key="vat_rate").confirmed)
        self.assertTrue(AppSetting.objects.get(key="crew_advance_pct").confirmed)
        konso = HotelBooking.objects.get(trip__code="GAD-TOUR-005", town="Konso")
        self.assertEqual(konso.price_status, "doubtful")
        sharaf = HotelBooking.objects.get(hotel_name="Sharaf Hotel")
        self.assertIsNone(sharaf.total_etb)  # USD with no rate: no invented ETB value
        self.assertEqual(Task.objects.filter(source_rule="import: pending item").count(), 7)
        self.assertTrue(Supplier.objects.get(code="S-006").needs_review)

    def test_editing_in_the_app_then_reimporting_keeps_blank_safe(self):
        self.run_import()
        s = Supplier.objects.get(code="S-002")
        self.assertTrue(s.phone)  # filled from the hotel contacts sheet
        self.run_import()
        s.refresh_from_db()
        self.assertTrue(s.phone)
