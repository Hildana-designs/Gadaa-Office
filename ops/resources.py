from ops import models as m
from ops.crud import Resource


class TripR(Resource):
    model = m.Trip
    slug = "trips"
    list_fields = ["code", "name", "client_name", "pax", "start_date", "end_date", "status", "price_etb"]
    search_fields = ["code", "name", "client_name", "route"]
    exclude = ("price_etb",)
    choice_lists = {"status": "Trip status", "currency": "Client currency"}
    trip_filter = False


class InquiryR(Resource):
    model = m.Inquiry
    slug = "inquiries"
    list_fields = ["code", "received_on", "partner", "pax", "route", "status", "quote_sent_on"]
    search_fields = ["code", "contact_text", "route", "notes"]
    exclude = ("code",)
    choice_lists = {"status": "Inquiry status"}
    trip_filter = False


class PartnerR(Resource):
    model = m.Partner
    slug = "partners"
    list_fields = ["name", "kind", "country", "language"]
    search_fields = ["name", "country", "email_domains"]
    trip_filter = False


class ContactR(Resource):
    model = m.Contact
    slug = "contacts"
    list_fields = ["name", "partner", "supplier", "role", "email", "phone"]
    search_fields = ["name", "email", "phone"]
    trip_filter = False


class SupplierR(Resource):
    model = m.Supplier
    slug = "suppliers"
    list_fields = ["code", "name", "town", "category", "phone", "rating", "needs_review"]
    search_fields = ["code", "name", "town", "category", "notes"]
    choice_lists = {"category": "Supplier category", "meal_plan": "Meal plan"}
    trip_filter = False


class SupplierRateR(Resource):
    model = m.SupplierRate
    slug = "supplier-rates"
    title = "Supplier rates"
    list_fields = ["supplier", "item", "amount", "currency", "kind", "valid_from", "valid_to"]
    search_fields = ["supplier__name", "item"]
    trip_filter = False


class FeeR(Resource):
    model = m.FeeReference
    slug = "fees"
    title = "Fees reference"
    list_fields = ["place", "item", "price_etb", "basis", "source", "status"]
    search_fields = ["place", "item", "source"]
    trip_filter = False


class HotelBookingR(Resource):
    model = m.HotelBooking
    slug = "hotel-bookings"
    list_fields = ["trip", "hotel_name", "town", "check_in", "check_out", "status", "total_etb", "release_deadline", "confirmation_no"]
    search_fields = ["hotel_name", "town", "confirmation_no", "trip__code"]
    choice_lists = {"status": "Booking status", "meal_plan": "Meal plan"}


class CrewR(Resource):
    model = m.CrewAssignment
    slug = "crew"
    title = "Crew"
    list_fields = ["trip", "role", "name", "days", "daily_rate", "total_fee", "advance_amount", "balance_amount", "balance_due_on", "balance_paid_on"]
    search_fields = ["name", "role", "trip__code"]
    choice_lists = {"role": "Crew role"}


class PassengerR(Resource):
    model = m.Passenger
    slug = "passengers"
    list_fields = ["trip", "number", "full_name", "nationality", "passport_no", "passport_expiry", "room_type"]
    search_fields = ["full_name", "trip__code"]
    sensitive = True


class PaymentR(Resource):
    model = m.Payment
    slug = "payments"
    list_fields = ["date", "trip", "direction", "counterparty", "currency", "amount", "fx_rate", "amount_etb", "proof_saved"]
    search_fields = ["counterparty", "description", "reference", "trip__code"]


class ExpenseR(Resource):
    model = m.Expense
    slug = "expenses"
    list_fields = ["trip", "ref", "date", "category", "description", "vendor", "amount_etb", "receipt_type", "status"]
    search_fields = ["description", "vendor", "reference", "trip__code"]
    exclude = ("client_uuid", "sync_status", "captured_at_local")
    choice_lists = {"category": "Cost category", "paid_by": "Paid by", "receipt_type": "Receipt type"}


class CostLineR(Resource):
    model = m.CostLine
    slug = "cost-lines"
    title = "Cost lines"
    list_fields = ["trip", "stage", "ref", "category", "description", "amount_etb", "status", "excluded"]
    search_fields = ["description", "category", "ref", "trip__code"]
    exclude = ("attributes", "hotel_booking", "crew_assignment", "expense")
    choice_lists = {"category": "Cost category", "basis": "Unit basis"}


class TaskR(Resource):
    model = m.Task
    slug = "tasks"
    list_fields = ["title", "trip", "due_date", "status", "source_rule"]
    search_fields = ["title", "trip__code"]
    exclude = ("source_key", "completed_at")


class DocumentR(Resource):
    model = m.Document
    slug = "documents"
    list_fields = ["title", "kind", "trip", "supplier", "sensitive"]
    search_fields = ["title", "kind", "trip__code"]

    def queryset(self, request):
        from core import roles

        qs = super().queryset(request)
        if not roles.can_see_passports(request.user):
            qs = qs.filter(sensitive=False)
        return qs


class ComplianceR(Resource):
    model = m.ComplianceItem
    slug = "compliance"
    title = "Compliance items"
    list_fields = ["title", "kind", "owner", "next_due", "status"]
    search_fields = ["title", "kind"]
    trip_filter = False


ALL = [TripR(), InquiryR(), PartnerR(), ContactR(), SupplierR(), SupplierRateR(), FeeR(), HotelBookingR(),
       CrewR(), PassengerR(), PaymentR(), ExpenseR(), CostLineR(), TaskR(), DocumentR(), ComplianceR()]
BY_SLUG = {r.slug: r for r in ALL}

NAV = [
    ("Trips", ["trips", "inquiries", "hotel-bookings", "crew", "passengers"]),
    ("Money", ["payments", "expenses", "cost-lines"]),
    ("People and suppliers", ["partners", "contacts", "suppliers", "supplier-rates", "fees"]),
    ("Office", ["tasks", "documents", "compliance"]),
]
