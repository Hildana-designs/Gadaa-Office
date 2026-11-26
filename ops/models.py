"""
Business records. Money is always an exact decimal. Wherever money can be in
another currency we keep the original amount, the currency and the exchange
rate beside the ETB value.
"""
import re
import uuid
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.crypto import EncryptedTextField

CENT = Decimal("0.01")
MONEY = dict(max_digits=16, decimal_places=2)
RATE = dict(max_digits=14, decimal_places=6)
TRIP_CODE_RE = re.compile(r"^GAD-TOUR-\d{3,}$")


def to_cents(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)


def etb(amount, fx_rate, currency="ETB"):
    """ETB value of an amount. None when a foreign amount has no real exchange rate yet."""
    if amount is None:
        return None
    if currency != "ETB" and (fx_rate is None or Decimal(fx_rate) == 1):
        return None
    return to_cents(Decimal(amount) * Decimal(fx_rate if currency != "ETB" else 1))


YES_NO_UNKNOWN = [("yes", "Yes"), ("no", "No"), ("unknown", "Not known")]
CURRENCIES = [("ETB", "ETB"), ("EUR", "EUR"), ("USD", "USD")]
RECORD_STATUS = [("confirmed", "Confirmed"), ("unconfirmed", "Unconfirmed"), ("doubtful", "Doubtful"), ("pending", "Pending")]


class Timestamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------- parties
class Partner(Timestamped):
    KIND = [("agency", "Partner agency"), ("direct", "Direct client")]
    name = models.CharField(max_length=200, unique=True)
    kind = models.CharField(max_length=10, choices=KIND, default="agency")
    country = models.CharField(max_length=80, blank=True)
    email_domains = models.CharField(max_length=300, blank=True, help_text="Comma-separated, for linking emails later.")
    language = models.CharField(max_length=10, choices=[("en", "English"), ("fr", "French")], default="en")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Supplier(Timestamped):
    code = models.CharField(max_length=20, unique=True, blank=True, help_text="For example S-001.")
    name = models.CharField(max_length=200)
    town = models.CharField("Destination / town", max_length=120, blank=True)
    category = models.CharField(max_length=60, blank=True)
    contact_person = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=200, blank=True)
    email = models.CharField(max_length=200, blank=True)
    meal_plan = models.CharField(max_length=20, blank=True)
    rates_include_vat = models.CharField(max_length=10, choices=YES_NO_UNKNOWN, default="unknown")
    rates_include_service = models.CharField(max_length=10, choices=YES_NO_UNKNOWN, default="unknown")
    foc_policy = models.CharField("FOC policy (guide / driver room)", max_length=300, blank=True)
    payment_terms = models.TextField(blank=True)
    payment_details = models.TextField(blank=True, help_text="Bank account or Telebirr details.")
    cancellation_terms = models.TextField(blank=True)
    tin_licence_verified = models.CharField(max_length=10, choices=YES_NO_UNKNOWN, default="unknown")
    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    last_used = models.DateField(null=True, blank=True)
    needs_review = models.BooleanField(default=False, help_text="For example a row naming several lodges.")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["town", "name"]

    def __str__(self):
        return f"{self.name} ({self.town})" if self.town else self.name

    def clean(self):
        if self.rating is not None and not 1 <= self.rating <= 5:
            raise ValidationError({"rating": "Rating is from 1 to 5."})


class Contact(Timestamped):
    name = models.CharField(max_length=200)
    partner = models.ForeignKey(Partner, null=True, blank=True, on_delete=models.CASCADE, related_name="contacts")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.CASCADE, related_name="contacts")
    role = models.CharField(max_length=120, blank=True)
    email = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=120, blank=True)
    language = models.CharField(max_length=10, choices=[("en", "English"), ("fr", "French"), ("am", "Amharic")], default="en")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class SupplierRate(Timestamped):
    KIND = [("contracted", "Contracted net rate"), ("quoted", "Quoted"), ("paid", "Paid on a past trip (not contracted)")]
    supplier = models.ForeignKey(Supplier, on_delete=models.CASCADE, related_name="rates")
    item = models.CharField(max_length=120, help_text="For example SGL room, DBL room, per day.")
    amount = models.DecimalField(**MONEY)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="ETB")
    basis = models.CharField(max_length=40, blank=True)
    meal_plan = models.CharField(max_length=20, blank=True)
    kind = models.CharField(max_length=12, choices=KIND, default="quoted")
    valid_from = models.DateField(null=True, blank=True)
    valid_to = models.DateField(null=True, blank=True)
    source_note = models.TextField(blank=True)

    class Meta:
        ordering = ["supplier", "item"]

    def __str__(self):
        return f"{self.supplier}: {self.item} {self.amount} {self.currency}"

    def clean(self):
        if self.valid_from and self.valid_to and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "End of validity is before the start."})


class FeeReference(Timestamped):
    place = models.CharField(max_length=120)
    item = models.CharField(max_length=300)
    price_etb = models.DecimalField("Price seen (ETB)", **MONEY)
    basis = models.CharField(max_length=120, blank=True)
    source = models.CharField(max_length=200, blank=True)
    verify_note = models.CharField("Verify before quoting?", max_length=300, blank=True)
    status = models.CharField(max_length=12, choices=RECORD_STATUS, default="unconfirmed")

    class Meta:
        ordering = ["place", "item"]

    def __str__(self):
        return f"{self.place}: {self.item}"


# ---------------------------------------------------------------- sales
class Inquiry(Timestamped):
    code = models.CharField(max_length=20, unique=True, blank=True)
    received_on = models.DateField(default=timezone.localdate)
    partner = models.ForeignKey(Partner, null=True, blank=True, on_delete=models.SET_NULL)
    contact_text = models.CharField("Contact person and email", max_length=300, blank=True)
    pax = models.PositiveIntegerField(null=True, blank=True)
    travel_dates_text = models.CharField(max_length=200, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    route = models.CharField("Route / interest", max_length=300, blank=True)
    status = models.CharField(max_length=30, default="New")
    quote_sent_on = models.DateField(null=True, blank=True)
    quote_value = models.DecimalField(null=True, blank=True, **MONEY)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="EUR")
    source = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-received_on", "-id"]
        verbose_name_plural = "inquiries"

    def __str__(self):
        return self.code or f"Inquiry {self.pk}"

    def save(self, *args, **kwargs):
        if not self.code:
            last = Inquiry.objects.filter(code__startswith="INQ-").order_by("-code").values_list("code", flat=True).first()
            n = int(last.split("-")[1]) + 1 if last and last.split("-")[1].isdigit() else 1
            self.code = f"INQ-{n:03d}"
        super().save(*args, **kwargs)


class Trip(Timestamped):
    code = models.CharField(max_length=20, unique=True, blank=True, help_text="GAD-TOUR-###. Left blank, the next number is used.")
    name = models.CharField(max_length=200, blank=True)
    partner = models.ForeignKey(Partner, null=True, blank=True, on_delete=models.SET_NULL)
    partner_ref = models.CharField("Partner's programme code", max_length=60, blank=True)
    client_name = models.CharField(max_length=200, blank=True)
    inquiry = models.ForeignKey(Inquiry, null=True, blank=True, on_delete=models.SET_NULL)
    pax = models.PositiveIntegerField(default=1)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    route = models.CharField(max_length=200, blank=True)
    route_family = models.CharField(max_length=80, blank=True, help_text="Used to compare similar trips (Phase 1).")
    status = models.CharField(max_length=30, default="Planning")
    price_amount = models.DecimalField("Price (total, client currency)", null=True, blank=True, **MONEY)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="EUR")
    fx_rate = models.DecimalField("Exchange rate (ETB per unit)", default=Decimal("1"), **RATE)
    fx_confirmed = models.BooleanField(default=False)
    price_etb = models.DecimalField("Price in ETB", null=True, blank=True, **MONEY)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-start_date", "-code"]

    def __str__(self):
        return f"{self.code} {self.name}".strip()

    def get_absolute_url(self):
        return reverse("ops:trip_detail", args=[self.pk])

    def clean(self):
        if self.code and not TRIP_CODE_RE.match(self.code):
            raise ValidationError({"code": "Trip code must look like GAD-TOUR-005."})
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValidationError({"end_date": "End date is before the start date."})

    def save(self, *args, **kwargs):
        if not self.code:
            numbers = [int(c.rsplit("-", 1)[1]) for c in Trip.objects.values_list("code", flat=True) if TRIP_CODE_RE.match(c)]
            self.code = f"GAD-TOUR-{(max(numbers) + 1 if numbers else 1):03d}"
        if self.price_amount is not None:
            self.price_etb = etb(self.price_amount, self.fx_rate, self.currency)
        super().save(*args, **kwargs)

    @property
    def days(self):
        if self.start_date and self.end_date:
            return (self.end_date - self.start_date).days + 1
        return None

    # Money summary. Cost lines are the trip's cost ledger (see DECISIONS.md).
    def cost_total_etb(self, stage="actual"):
        lines = self.cost_lines.filter(stage=stage, excluded=False)
        return to_cents(sum((l.amount_etb or Decimal("0")) for l in lines))

    def recoverable_etb(self, stage="actual"):
        lines = self.cost_lines.filter(stage=stage, excluded=False, recoverable=True)
        return to_cents(sum((l.amount_etb or Decimal("0")) for l in lines))

    def net_cost_etb(self, stage="actual"):
        return self.cost_total_etb(stage) - self.recoverable_etb(stage)

    def received_etb(self):
        return to_cents(sum((p.amount_etb or 0) for p in self.payments.filter(direction="in")))

    def profit_etb(self):
        if self.price_etb is None:
            return None
        return self.price_etb - self.net_cost_etb()

    def margin(self):
        if not self.price_etb:
            return None
        return (self.profit_etb() / self.price_etb).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


class Quote(Timestamped):
    ref = models.CharField(max_length=30, unique=True)
    inquiry = models.ForeignKey(Inquiry, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes")
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.SET_NULL, related_name="quotes")
    pax = models.PositiveIntegerField(default=2)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="EUR")
    target_margin = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    contingency_pct = models.DecimalField(max_digits=6, decimal_places=4, null=True, blank=True)
    status = models.CharField(max_length=20, default="Draft")
    sent_on = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.ref


class HotelBooking(Timestamped):
    ref = models.CharField("Booking ref", max_length=30, blank=True)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="hotel_bookings")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL)
    hotel_name = models.CharField(max_length=200)
    town = models.CharField(max_length=120, blank=True)
    check_in = models.DateField()
    check_out = models.DateField()
    sgl_rooms = models.PositiveSmallIntegerField(default=0)
    dbl_rooms = models.PositiveSmallIntegerField(default=0)
    twn_rooms = models.PositiveSmallIntegerField(default=0)
    room_description = models.CharField(max_length=120, blank=True)
    meal_plan = models.CharField(max_length=20, blank=True)
    rate_per_night = models.DecimalField("Rate per night (all rooms)", null=True, blank=True, **MONEY)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="ETB")
    fx_rate = models.DecimalField(default=Decimal("1"), **RATE)
    total_amount = models.DecimalField("Total (original currency)", null=True, blank=True, **MONEY)
    total_etb = models.DecimalField("Total (ETB)", null=True, blank=True, **MONEY)
    status = models.CharField(max_length=20, default="Requested")
    confirmation_no = models.CharField(max_length=120, blank=True)
    release_deadline = models.DateField("Release / cancellation deadline", null=True, blank=True)
    voucher_sent = models.BooleanField(default=False)
    paid = models.CharField(max_length=10, choices=YES_NO_UNKNOWN, default="no")
    rooming_list_sent = models.BooleanField(default=False)
    payment_details = models.TextField(blank=True)
    price_status = models.CharField(max_length=12, choices=RECORD_STATUS, default="confirmed")
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["check_in"]

    def __str__(self):
        return f"{self.trip.code} {self.hotel_name} {self.check_in:%d %b}"

    @property
    def nights(self):
        return (self.check_out - self.check_in).days

    def clean(self):
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError({"check_out": "Check-out must be after check-in."})

    def save(self, *args, **kwargs):
        if self.total_amount is None and self.rate_per_night is not None and self.check_in and self.check_out:
            self.total_amount = to_cents(self.rate_per_night * self.nights)
        if self.total_amount is not None and self.total_etb is None:
            self.total_etb = etb(self.total_amount, self.fx_rate, self.currency)
        super().save(*args, **kwargs)


class CrewAssignment(Timestamped):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="crew")
    role = models.CharField(max_length=40)
    name = models.CharField(max_length=200, blank=True)
    phone = models.CharField(max_length=60, blank=True)
    licence_id_no = EncryptedTextField("Licence / ID no.", blank=True)
    licence_expiry = models.DateField(null=True, blank=True)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    days = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Left blank, counted from the dates.")
    daily_rate = models.DecimalField("Daily rate (ETB)", null=True, blank=True, **MONEY)
    rate_status = models.CharField(max_length=12, choices=RECORD_STATUS, default="confirmed")
    advance_pct = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.40"))
    total_fee = models.DecimalField(null=True, blank=True, editable=False, **MONEY)
    advance_amount = models.DecimalField(null=True, blank=True, editable=False, **MONEY)
    balance_amount = models.DecimalField(null=True, blank=True, editable=False, **MONEY)
    advance_paid_on = models.DateField(null=True, blank=True)
    balance_due_on = models.DateField(null=True, blank=True, editable=False)
    balance_paid_on = models.DateField(null=True, blank=True)
    agreement_signed = models.BooleanField(default=False)
    tin_bank_collected = models.BooleanField(default=False)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["trip", "role"]

    def __str__(self):
        return f"{self.trip.code} {self.role} {self.name}".strip()

    def save(self, *args, **kwargs):
        from ops.rules import crew_payment_schedule

        if self.days is None and self.start_date and self.end_date:
            self.days = (self.end_date - self.start_date).days + 1
        sched = crew_payment_schedule(self.days, self.daily_rate, self.advance_pct, self.end_date)
        self.total_fee, self.advance_amount, self.balance_amount, self.balance_due_on = sched
        super().save(*args, **kwargs)


class Passenger(Timestamped):
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="passengers")
    number = models.PositiveSmallIntegerField(default=1)
    full_name = models.CharField("Full name (as in passport)", max_length=200)
    nationality = models.CharField(max_length=80, blank=True)
    passport_no = EncryptedTextField("Passport no.", blank=True)
    passport_expiry = models.DateField(null=True, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    room_type = models.CharField(max_length=20, blank=True)
    sharing_with = models.CharField(max_length=200, blank=True)
    dietary_needs = models.CharField(max_length=300, blank=True)
    medical = EncryptedTextField("Allergies / medical conditions", blank=True)
    emergency_contact = models.CharField(max_length=300, blank=True)
    arrival_flight = models.CharField(max_length=120, blank=True)
    departure_flight = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["trip", "number"]

    def __str__(self):
        return f"{self.trip.code} {self.full_name}"


class Payment(Timestamped):
    DIRECTION = [("in", "In (received)"), ("out", "Out (paid)")]
    date = models.DateField(default=timezone.localdate)
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.SET_NULL, related_name="payments")
    direction = models.CharField(max_length=3, choices=DIRECTION)
    counterparty = models.CharField("Paid by / paid to", max_length=200)
    description = models.CharField(max_length=300, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="ETB")
    amount = models.DecimalField(**MONEY)
    fx_rate = models.DecimalField("Exchange rate to ETB", default=Decimal("1"), **RATE)
    amount_etb = models.DecimalField("ETB equivalent", null=True, blank=True, editable=False, **MONEY)
    method = models.CharField(max_length=60, blank=True)
    reference = models.CharField("Reference / transaction no.", max_length=120, blank=True)
    proof_saved = models.BooleanField(default=False)
    proof = models.FileField(upload_to="payments/%Y/", blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.date} {self.get_direction_display()} {self.amount} {self.currency}"

    def save(self, *args, **kwargs):
        self.amount_etb = etb(self.amount, self.fx_rate, self.currency)
        super().save(*args, **kwargs)

    def clean(self):
        if self.currency != "ETB" and (self.fx_rate is None or self.fx_rate == 1):
            raise ValidationError({"fx_rate": "Enter the exchange rate used for this payment."})


class Expense(Timestamped):
    STATUS = [("included", "Included"), ("excluded", "Excluded (not a trip cost)"), ("pending", "Pending")]
    SYNC = [("synced", "Synced"), ("pending", "Waiting to sync")]

    ref = models.CharField(max_length=20, blank=True)
    trip = models.ForeignKey(Trip, on_delete=models.CASCADE, related_name="expenses")
    date = models.DateField(null=True, blank=True)
    trip_day = models.PositiveSmallIntegerField(null=True, blank=True)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=400)
    vendor = models.CharField("Supplier / shop", max_length=200, blank=True)
    location = models.CharField(max_length=120, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="ETB")
    amount = models.DecimalField(null=True, blank=True, **MONEY)
    fx_rate = models.DecimalField(default=Decimal("1"), **RATE)
    fx_confirmed = models.BooleanField(default=True)
    amount_etb = models.DecimalField(null=True, blank=True, **MONEY)
    paid_by = models.CharField(max_length=60, blank=True)
    receipt_type = models.CharField(max_length=60, blank=True)
    receipt_status = models.CharField("Receipt filed?", max_length=10, choices=YES_NO_UNKNOWN, default="unknown")
    receipt_file = models.FileField(upload_to="receipts/%Y/", blank=True)
    reference = models.CharField(max_length=200, blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="included")
    recoverable = models.BooleanField("Recoverable from guests", default=False)
    flag = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)
    # Ready for offline capture later (Phase 4).
    client_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    captured_at_local = models.DateTimeField("Captured at (local time)", null=True, blank=True)
    sync_status = models.CharField(max_length=10, choices=SYNC, default="synced")

    class Meta:
        ordering = ["trip", "date", "ref"]

    def __str__(self):
        return f"{self.trip.code} {self.ref} {self.description[:40]}"

    def save(self, *args, **kwargs):
        if self.amount is not None and self.amount_etb is None:
            self.amount_etb = etb(self.amount, self.fx_rate, self.currency)
        if self.captured_at_local is None:
            self.captured_at_local = timezone.now()
        super().save(*args, **kwargs)


class CostLine(Timestamped):
    """
    One line of what a trip costs (stage=actual) or was budgeted to cost
    (stage=budget). This is the ledger the profit page and the Cost Hub use.
    Hotel bookings, crew and expenses each link to the line they produced.
    """

    STAGE = [("budget", "Budget / quote"), ("actual", "Actual")]
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.CASCADE, related_name="cost_lines")
    quote = models.ForeignKey(Quote, null=True, blank=True, on_delete=models.CASCADE, related_name="cost_lines")
    stage = models.CharField(max_length=10, choices=STAGE, default="actual")
    ref = models.CharField(max_length=20, blank=True)
    category = models.CharField(max_length=80)
    description = models.CharField(max_length=400)
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.SET_NULL)
    place = models.CharField(max_length=120, blank=True)
    unit_cost = models.DecimalField(null=True, blank=True, **MONEY)
    units = models.DecimalField(null=True, blank=True, max_digits=10, decimal_places=3)
    times = models.DecimalField(null=True, blank=True, max_digits=10, decimal_places=3)
    basis = models.CharField(max_length=40, blank=True)
    currency = models.CharField(max_length=3, choices=CURRENCIES, default="ETB")
    amount = models.DecimalField("Amount (original currency)", null=True, blank=True, **MONEY)
    fx_rate = models.DecimalField(default=Decimal("1"), **RATE)
    amount_etb = models.DecimalField("Amount (ETB)", null=True, blank=True, **MONEY)
    includes_vat = models.CharField(max_length=10, choices=YES_NO_UNKNOWN, default="unknown")
    who_pays = models.CharField(max_length=40, blank=True)
    status = models.CharField(max_length=12, choices=RECORD_STATUS, default="confirmed")
    receipt_status = models.CharField(max_length=10, choices=YES_NO_UNKNOWN, default="unknown")
    recoverable = models.BooleanField(default=False)
    excluded = models.BooleanField(default=False)
    attributes = models.JSONField(default=dict, blank=True)
    hotel_booking = models.OneToOneField(HotelBooking, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_line")
    crew_assignment = models.OneToOneField(CrewAssignment, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_line")
    expense = models.OneToOneField(Expense, null=True, blank=True, on_delete=models.SET_NULL, related_name="cost_line")
    source_ref = models.CharField(max_length=200, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["trip", "stage", "category", "ref"]

    def __str__(self):
        return f"{self.category}: {self.description[:50]}"

    def save(self, *args, **kwargs):
        if self.amount is None and self.unit_cost is not None:
            self.amount = to_cents(self.unit_cost * (self.units or 1) * (self.times or 1))
        if self.amount is not None and self.amount_etb is None:
            self.amount_etb = etb(self.amount, self.fx_rate, self.currency)
        super().save(*args, **kwargs)


class Task(Timestamped):
    STATUS = [("open", "Open"), ("done", "Done"), ("cancelled", "Cancelled")]
    title = models.CharField(max_length=300)
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.CASCADE, related_name="tasks")
    due_date = models.DateField(null=True, blank=True)
    source_rule = models.CharField(max_length=80, blank=True)
    source_key = models.CharField(max_length=200, blank=True, db_index=True, help_text="Stops rules creating duplicates.")
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    completed_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["status", "due_date"]

    def __str__(self):
        return self.title


class ComplianceItem(Timestamped):
    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=60, help_text="Tax filing, licence, insurance, passport, retention...")
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    due_rule = models.CharField(max_length=300, blank=True, help_text="Left empty until an accountant or the Ministry confirms it.")
    next_due = models.DateField(null=True, blank=True)
    reminder_days = models.PositiveSmallIntegerField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=RECORD_STATUS, default="unconfirmed")
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.title


class ComplianceEvent(Timestamped):
    item = models.ForeignKey(ComplianceItem, on_delete=models.CASCADE, related_name="events")
    date = models.DateField()
    note = models.TextField(blank=True)
    evidence = models.FileField(upload_to="compliance/%Y/", blank=True)

    def __str__(self):
        return f"{self.item} {self.date}"


class Document(Timestamped):
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.CASCADE, related_name="documents")
    supplier = models.ForeignKey(Supplier, null=True, blank=True, on_delete=models.CASCADE)
    kind = models.CharField(max_length=60, help_text="Contract, voucher, passport copy, receipt...")
    title = models.CharField(max_length=200)
    file = models.FileField(upload_to="documents/%Y/")
    sensitive = models.BooleanField(default=False, help_text="Passport or ID copy: hidden from the Accountant role.")
    notes = models.TextField(blank=True)

    def __str__(self):
        return self.title


class EmailMessage(Timestamped):
    """Filled by the inbox reader in Phase 3."""
    message_id = models.CharField(max_length=500, unique=True)
    folder = models.CharField(max_length=120, default="INBOX")
    uid = models.CharField(max_length=40, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    from_address = models.CharField(max_length=300, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body_text = models.TextField(blank=True)
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.SET_NULL)
    classification = models.CharField(max_length=40, blank=True)
    urgency = models.CharField(max_length=2, blank=True)
    decided_by_rule = models.CharField(max_length=200, blank=True)
    needs_review = models.BooleanField(default=False)

    def __str__(self):
        return self.subject


class Draft(Timestamped):
    STATUS = [("draft", "Draft"), ("approved", "Approved"), ("saved", "Saved to mailbox Drafts"), ("sent", "Sent")]
    template_code = models.CharField(max_length=20, blank=True)
    language = models.CharField(max_length=2, choices=[("en", "English"), ("fr", "French")], default="en")
    trip = models.ForeignKey(Trip, null=True, blank=True, on_delete=models.SET_NULL)
    reply_to = models.ForeignKey(EmailMessage, null=True, blank=True, on_delete=models.SET_NULL)
    to_address = models.CharField(max_length=500, blank=True)
    subject = models.CharField(max_length=500, blank=True)
    body = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="draft")
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)

    def __str__(self):
        return self.subject or f"Draft {self.pk}"
