"""Login, two-factor codes, roles, encryption and the activity log. Made-up data only."""
from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import connection
from django.test import TestCase, override_settings
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.models import AuditLog, Role
from ops.models import Passenger, Trip


def make_user(username, role):
    user = get_user_model().objects.create_user(username, password="a-long-test-password")
    user.groups.add(Group.objects.get_or_create(name=role)[0])
    return user


@override_settings(GADAA_MFA_REQUIRED=False)
class Roles(TestCase):
    def setUp(self):
        self.trip = Trip.objects.create(name="Test trip", start_date=date(2027, 1, 1), end_date=date(2027, 1, 5))
        self.pax = Passenger.objects.create(trip=self.trip, full_name="Test PERSON", passport_no="X1234567")

    def login(self, role):
        user = make_user(role.lower(), role)
        self.client.force_login(user)
        return user

    def test_login_required(self):
        r = self.client.get(reverse("ops:trips_list"))
        self.assertEqual(r.status_code, 302)
        self.assertIn(reverse("core:login"), r["Location"])

    def test_accountant_reads_but_cannot_change(self):
        self.login(Role.ACCOUNTANT)
        self.assertEqual(self.client.get(reverse("ops:trips_list")).status_code, 200)
        self.assertEqual(self.client.get(self.trip.get_absolute_url()).status_code, 200)
        r = self.client.post(reverse("ops:trips_edit", args=[self.trip.pk]), {"name": "changed"})
        self.assertEqual(r.status_code, 403)
        self.trip.refresh_from_db()
        self.assertEqual(self.trip.name, "Test trip")

    def test_accountant_never_sees_passports(self):
        self.login(Role.ACCOUNTANT)
        self.assertEqual(self.client.get(reverse("ops:passengers_list")).status_code, 403)
        self.assertEqual(self.client.get(reverse("ops:passengers_edit", args=[self.pax.pk])).status_code, 403)
        self.assertNotContains(self.client.get(self.trip.get_absolute_url()), "X1234567")

    def test_operations_can_edit_and_passport_view_is_logged(self):
        self.login(Role.OPERATIONS)
        r = self.client.get(reverse("ops:passengers_edit", args=[self.pax.pk]))
        self.assertEqual(r.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="view_sensitive", object_id=str(self.pax.pk)).exists())
        lst = self.client.get(reverse("ops:passengers_list"))
        self.assertNotContains(lst, "X1234567")  # masked in lists
        self.assertContains(lst, "567")

    def test_only_admin_manages_users_and_backups(self):
        self.login(Role.OPERATIONS)
        self.assertEqual(self.client.get(reverse("core:users")).status_code, 403)
        self.assertEqual(self.client.get(reverse("core:backups")).status_code, 403)
        self.client.logout()
        self.login(Role.ADMIN)
        self.assertEqual(self.client.get(reverse("core:users")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:backups")).status_code, 200)

    def test_only_admin_deletes(self):
        self.login(Role.OPERATIONS)
        self.assertEqual(self.client.post(reverse("ops:trips_delete", args=[self.trip.pk])).status_code, 403)

    def test_every_list_and_form_opens(self):
        from ops.resources import ALL

        self.login(Role.ADMIN)
        for r in ALL:
            self.assertEqual(self.client.get(reverse(f"ops:{r.slug}_list")).status_code, 200, r.slug)
            self.assertEqual(self.client.get(reverse(f"ops:{r.slug}_new")).status_code, 200, r.slug)
        self.assertEqual(self.client.get(reverse("core:home")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:settings")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:activity")).status_code, 200)

    def test_htmx_search_returns_rows_only(self):
        self.login(Role.OPERATIONS)
        r = self.client.get(reverse("ops:trips_list"), {"q": "Test"}, HTTP_HX_REQUEST="true")
        self.assertContains(r, "Test trip")
        self.assertNotContains(r, "<html")


class TwoFactor(TestCase):
    def test_first_login_must_set_up_code_then_verify(self):
        user = make_user("ops", Role.OPERATIONS)
        r = self.client.post(reverse("core:login"), {"username": "ops", "password": "a-long-test-password"})
        self.assertEqual(r.status_code, 302)
        r = self.client.get(reverse("ops:trips_list"))
        self.assertRedirects(r, reverse("core:mfa_setup"), fetch_redirect_response=False)
        self.client.get(reverse("core:mfa_setup"))
        device = TOTPDevice.objects.get(user=user)
        totp = TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift)
        r = self.client.post(reverse("core:mfa_setup"), {"code": f"{totp.token():06d}"})
        self.assertRedirects(r, reverse("core:home"), fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("ops:trips_list")).status_code, 200)

    def test_wrong_code_is_refused_and_logged(self):
        user = make_user("ops2", Role.OPERATIONS)
        TOTPDevice.objects.create(user=user, name="Phone", confirmed=True)
        self.client.post(reverse("core:login"), {"username": "ops2", "password": "a-long-test-password"})
        r = self.client.get(reverse("ops:trips_list"))
        self.assertIn(reverse("core:mfa_verify"), r["Location"])
        r = self.client.post(reverse("core:mfa_verify"), {"code": "000000"})
        self.assertEqual(r.status_code, 200)
        self.assertTrue(AuditLog.objects.filter(action="login_failed", user=user).exists())
        self.assertEqual(self.client.get(reverse("ops:trips_list")).status_code, 302)

    def test_bad_password_is_logged(self):
        make_user("ops3", Role.OPERATIONS)
        self.client.post(reverse("core:login"), {"username": "ops3", "password": "wrong"})
        self.assertTrue(AuditLog.objects.filter(action="login_failed").exists())


class Encryption(TestCase):
    def test_passport_number_is_encrypted_in_the_database(self):
        trip = Trip.objects.create()
        p = Passenger.objects.create(trip=trip, full_name="Made UP", passport_no="P9988776", medical="none")
        with connection.cursor() as cur:
            cur.execute("SELECT passport_no, medical FROM ops_passenger WHERE id = %s", [p.pk])
            raw_passport, raw_medical = cur.fetchone()
        self.assertNotIn("P9988776", raw_passport)
        self.assertTrue(raw_passport.startswith("enc1:"))
        self.assertTrue(raw_medical.startswith("enc1:"))
        self.assertEqual(Passenger.objects.get(pk=p.pk).passport_no, "P9988776")

    def test_activity_log_never_holds_the_passport_number(self):
        trip = Trip.objects.create()
        Passenger.objects.create(trip=trip, full_name="Made UP", passport_no="P9988776")
        for entry in AuditLog.objects.all():
            self.assertNotIn("P9988776", str(entry.changes))

    def test_amharic_text_round_trips(self):
        trip = Trip.objects.create(name="የኦሞ ሸለቆ ጉዞ", notes="ጋዳ ፎቶግራፊ")
        self.assertEqual(Trip.objects.get(pk=trip.pk).name, "የኦሞ ሸለቆ ጉዞ")


@override_settings(GADAA_MFA_REQUIRED=False)
class ActivityLog(TestCase):
    def test_create_change_delete_are_logged_with_user(self):
        admin = make_user("boss", Role.ADMIN)
        self.client.force_login(admin)
        self.client.post(reverse("ops:partners_new"), {"name": "Example Agency", "kind": "agency", "language": "fr"})
        from ops.models import Partner

        partner = Partner.objects.get(name="Example Agency")
        self.client.post(reverse("ops:partners_edit", args=[partner.pk]),
                         {"name": "Example Agency SARL", "kind": "agency", "language": "fr"})
        self.client.post(reverse("ops:partners_delete", args=[partner.pk]))
        actions = list(AuditLog.objects.filter(object_id=str(partner.pk), content_type__model="partner")
                       .values_list("action", "username"))
        self.assertIn(("create", "boss"), actions)
        self.assertIn(("update", "boss"), actions)
        self.assertIn(("delete", "boss"), actions)
        update = AuditLog.objects.get(action="update", content_type__model="partner")
        self.assertEqual(update.changes["name"], ["Example Agency", "Example Agency SARL"])
