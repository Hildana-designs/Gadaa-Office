from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase

from ops.models import CostLine, CrewAssignment, HotelBooking, Payment, Trip, etb
from ops.rules import add_business_days, crew_payment_schedule, fuel_cost, margin_on_price, markup_on_cost, quote_price


class BusinessDays(TestCase):
    def test_skips_sundays_only(self):
        # Wed 25 Nov 2026 + 7 working days, Sundays off: Thu..Sat (3), Mon..Thu (4) = Thu 3 Dec.
        self.assertEqual(add_business_days(date(2026, 11, 25), 7), date(2026, 12, 3))

    def test_matches_excel_workday_intl_11(self):
        # Sat 24 Oct 2026 + 7 -> Mon 26..Sat 31 (6) + Mon 2 Nov = 2 Nov
        self.assertEqual(add_business_days(date(2026, 10, 24), 7), date(2026, 11, 2))
        # Saturday counts as a working day
        self.assertEqual(add_business_days(date(2026, 11, 20), 1), date(2026, 11, 21))
        # Starting on a Saturday skips the Sunday
        self.assertEqual(add_business_days(date(2026, 11, 21), 1), date(2026, 11, 23))


class CrewSchedule(TestCase):
    def test_40_60_split_exact(self):
        total, adv, bal, due = crew_payment_schedule(15, Decimal("5500"), Decimal("0.40"), date(2026, 11, 25))
        self.assertEqual(total, Decimal("82500.00"))
        self.assertEqual(adv, Decimal("33000.00"))
        self.assertEqual(bal, Decimal("49500.00"))
        self.assertEqual(adv + bal, total)
        self.assertEqual(due, date(2026, 12, 3))

    def test_odd_amount_never_loses_a_cent(self):
        total, adv, bal, _ = crew_payment_schedule(3, Decimal("3333.33"), Decimal("0.40"), date(2026, 1, 1))
        self.assertEqual(adv + bal, total)

    def test_no_rate_means_no_money(self):
        total, adv, bal, due = crew_payment_schedule(None, None, Decimal("0.40"), date(2026, 10, 25))
        self.assertIsNone(total)
        self.assertEqual(due, date(2026, 11, 2))

    def test_model_fills_schedule(self):
        trip = Trip.objects.create(code="GAD-TOUR-900", start_date=date(2026, 10, 17), end_date=date(2026, 10, 25))
        crew = CrewAssignment.objects.create(trip=trip, role="Driver", start_date=date(2026, 10, 17),
                                             end_date=date(2026, 10, 25), daily_rate=Decimal("10000"))
        self.assertEqual(crew.days, 9)
        self.assertEqual(crew.total_fee, Decimal("90000.00"))
        self.assertEqual(crew.advance_amount, Decimal("36000.00"))
        self.assertEqual(crew.balance_amount, Decimal("54000.00"))


class Fuel(TestCase):
    def test_trip005_fuel(self):
        self.assertEqual(fuel_cost(2031, 7, Decimal("183.49")), Decimal("53238.31"))

    def test_detour_allowance(self):
        # Workbook example: 105 km +10% / 7 x 183.49
        self.assertEqual(fuel_cost(105, 7, Decimal("183.49"), Decimal("0.10")), Decimal("3027.59"))


class Pricing(TestCase):
    def test_margin_vs_markup(self):
        self.assertEqual(markup_on_cost(130, 100), Decimal("0.3"))
        self.assertEqual(round(margin_on_price(130, 100), 3), Decimal("0.231"))

    def test_price_formula_follows_trip_costing_sheet(self):
        r = quote_price(direct_cost=Decimal("100000"), contingency_pct=Decimal("0.05"), margin=Decimal("0.30"),
                        vat_rate=Decimal("0.15"), claims_input_vat=False, charges_output_vat=False,
                        vat_inclusive_cost=0, expected_rate=Decimal("184"), fx_buffer=Decimal("0.03"), pax=2)
        # 105,000 / 0.7 = 150,000 ETB; 150,000 / (184 x 0.97) / 2 = 420.21 -> rounded up to 425 EUR
        self.assertEqual(r["total_cost"], Decimal("105000"))
        self.assertEqual(r["price_before_vat"], Decimal("150000"))
        self.assertEqual(r["price_per_person"], Decimal("425"))
        self.assertEqual(r["total_quoted"], Decimal("850"))
        self.assertGreaterEqual(r["margin"], Decimal("0.30"))

    def test_vat_switches(self):
        r = quote_price(direct_cost=Decimal("115000"), contingency_pct=Decimal("0"), margin=Decimal("0.30"),
                        vat_rate=Decimal("0.15"), claims_input_vat=True, charges_output_vat=True,
                        vat_inclusive_cost=Decimal("115000"), expected_rate=Decimal("1"), fx_buffer=Decimal("0"), pax=1, round_to=1)
        self.assertEqual(r["input_vat"].quantize(Decimal("0.01")), Decimal("15000.00"))
        self.assertEqual(r["net_cost"].quantize(Decimal("0.01")), Decimal("100000.00"))
        self.assertEqual(r["output_vat"].quantize(Decimal("0.01")), Decimal("21428.57"))


class MoneyAndCodes(TestCase):
    def test_foreign_amount_without_rate_has_no_etb_value(self):
        self.assertIsNone(etb(Decimal("60"), Decimal("1"), "USD"))
        self.assertEqual(etb(Decimal("60"), Decimal("161.5"), "USD"), Decimal("9690.00"))

    def test_trip_codes(self):
        a = Trip.objects.create()
        b = Trip.objects.create()
        self.assertEqual(a.code, "GAD-TOUR-001")
        self.assertEqual(b.code, "GAD-TOUR-002")
        bad = Trip(code="TOUR-5")
        with self.assertRaises(ValidationError):
            bad.full_clean()

    def test_payment_needs_rate_for_foreign_currency(self):
        p = Payment(direction="in", counterparty="Partner", currency="EUR", amount=Decimal("100"), fx_rate=Decimal("1"))
        with self.assertRaises(ValidationError):
            p.full_clean()
        p.fx_rate = Decimal("184")
        p.save()
        self.assertEqual(p.amount_etb, Decimal("18400.00"))

    def test_hotel_total_from_nights(self):
        trip = Trip.objects.create()
        h = HotelBooking.objects.create(trip=trip, hotel_name="Test Lodge", check_in=date(2026, 11, 14),
                                        check_out=date(2026, 11, 16), rate_per_night=Decimal("17761.70"))
        self.assertEqual(h.nights, 2)
        self.assertEqual(h.total_etb, Decimal("35523.40"))

    def test_trip_profit_excludes_excluded_and_recoverable(self):
        trip = Trip.objects.create(price_amount=Decimal("1000"), currency="ETB")
        CostLine.objects.create(trip=trip, category="Fuel", description="a", amount=Decimal("300"))
        CostLine.objects.create(trip=trip, category="Other", description="beer", amount=Decimal("50"), recoverable=True)
        CostLine.objects.create(trip=trip, category="Other", description="stickers", amount=Decimal("99"), excluded=True)
        self.assertEqual(trip.cost_total_etb(), Decimal("350.00"))
        self.assertEqual(trip.net_cost_etb(), Decimal("300.00"))
        self.assertEqual(trip.profit_etb(), Decimal("700.00"))
        self.assertEqual(trip.margin(), Decimal("0.7000"))
