"""
Import the trip files: Trip 005 management cost analysis, the Surma (Trip 001)
expense analysis and the November 2026 hotel bookings sheet.
"""
from datetime import date, timedelta
from decimal import Decimal

import openpyxl

from ops.importer.base import as_date, dec, money, text, upsert
from ops.models import CostLine, CrewAssignment, Expense, HotelBooking, Partner, Supplier, Task, Trip, to_cents
from ops.rules import fuel_cost

ATE = {"name": "Aisha Tours Ethiopia (ATE)", "kind": "agency", "country": "France", "language": "fr",
       "notes": "French agency: sells the trips and holds the client relationship (ATE-GADAA procedure, 1 Oct 2026)."}

# Ground-cost categories in the Trip 005 file -> the workbook's cost categories.
T005_CATEGORY = {"Guide meals": "Guide and crew meals"}

# Surma file categories -> the workbook's cost categories. The original is kept on each line.
SURMA_CATEGORY = {
    "Accommodation": "Hotels (lodging)",
    "Food Supplies & Groceries": "Client meals",
    "Restaurant & Café Meals": "Client meals",
    "Camp & Household Supplies": "Other",
    "Alcohol (Recoverable from Guests)": "Other",
    "Printing & Branding": "Other",
    "Guide, Community & Entrance Fees": "Entrances and village fees",
    "Domestic Flights": "Domestic flights",
}
DOCUMENTED = {"Fiscal receipt", "Manual receipt only", "Ticket only", "Bank transfer"}


def _supplier_for(town, hotel):
    """Match a hotel to a supplier from the workbook by town and first word of the name."""
    key = hotel.split("/")[0].split(" or ")[0].replace("Guest House (", "").strip().lower()
    for s in Supplier.objects.all():
        if key[:8] and key[:8] in s.name.lower() and (not town or town.lower()[:4] in (s.town or "").lower()[:4] or True):
            if town and s.town and town.lower()[:4] != s.town.lower()[:4]:
                continue
            return s
    return None


# ---------------------------------------------------------------- Trip 005
def import_trip005(path, report):
    wb = openpyxl.load_workbook(path, data_only=True)
    src = "Trip 005 cost analysis"
    summary = wb["Summary"]
    inputs = {}
    for row in summary.iter_rows(min_row=1, max_row=15, values_only=True):
        if row[0] and row[1] is not None and isinstance(row[1], (int, float)):
            inputs[text(row[0])] = row[1]
    sales = money(inputs["Sales for this trip (ETB)"])
    days = int(inputs["Trip days"])
    guide_rate = money(inputs["Guide daily rate"])
    driver_rate = money(inputs["Driver daily rate"])
    km = dec(inputs["Total route (km)"])
    kmpl = dec(inputs["Car consumption (km per litre)"])
    fuel_price = dec(inputs["Fuel price (ETB per litre)"])

    partner = upsert(report, "partner:ate", Partner, ATE, lookup={"name": ATE["name"]})
    start = date(2026, 11, 11)
    end = start + timedelta(days=days - 1)
    trip = upsert(report, "trip:GAD-TOUR-005", Trip, {
        "code": "GAD-TOUR-005", "name": "The Peoples of the Omo Valley and Harar", "partner": partner,
        "partner_ref": "ATE101", "client_name": "Mr and Mrs Cheret", "pax": 2, "start_date": start, "end_date": end,
        "route": "Addis Ababa, Langano, Arba Minch, Jinka, Turmi, Konso, Hawassa, Harar, Dire Dawa",
        "route_family": "Omo Valley and Harar", "status": "Completed", "price_amount": sales, "currency": "ETB",
        "fx_rate": Decimal("1"), "fx_confirmed": True,
        "notes": ("Imported from the manager's cost analysis. Not in the cost: the guide sheet's 10,000 ETB contingency, "
                  "guide domestic flights, visas, insurance, tips, photo and Ukuli fees paid by the client. "
                  "Land Cruiser costed as driver plus fuel only."),
    }, lookup={"code": "GAD-TOUR-005"})
    report.doubt(f"{src}", "Trip status set to 'Completed' because the trip ended on 25 Nov; the file does not say")

    # Hotels
    ws = wb["Hotels"]
    for i, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
        town, hotel, check_in, nights, rate, currency, total_orig, implied, total_etb = row[:9]
        if not hotel or not isinstance(nights, (int, float)):
            continue
        where = f"{src} Hotels row {i} ({hotel})"
        check_in = as_date(check_in)
        total_etb = money(total_etb)
        fx = Decimal("1") if currency == "ETB" else (to_cents(total_etb) / money(total_orig)).quantize(Decimal("0.000001"))
        price_status = "confirmed"
        notes = []
        if currency == "USD":
            notes.append(f"ETB total is the manager's figure; rate worked out as {fx} ETB per USD.")
        if "Konso" in text(town):
            price_status = "doubtful"
            notes.append("Bookings sheet says 76 USD; this file says 78 USD.")
            report.doubt(where, "78 USD here, 76 USD in the bookings sheet")
        if "Radisson" in text(hotel):
            price_status = "doubtful"
            notes.append("Bookings sheet says 173 USD; this file says 198 USD.")
            report.doubt(where, "198 USD here, 173 USD in the bookings sheet")
        if "Alpha" in text(hotel):
            price_status = "doubtful"
            notes.append("Bookings sheet has no price for this stay.")
            report.doubt(where, "8,000 ETB a night here, no price in the bookings sheet")
        supplier = _supplier_for(text(town), text(hotel))
        hb = upsert(report, f"t005:hotel:{i}", HotelBooking, {
            "trip": trip, "supplier": supplier, "hotel_name": text(hotel), "town": text(town), "check_in": check_in,
            "check_out": check_in + timedelta(days=int(nights)), "room_description": "King size (2 guests)",
            "rate_per_night": money(rate), "currency": text(currency), "fx_rate": fx, "total_amount": money(total_orig),
            "total_etb": total_etb, "status": "Confirmed", "price_status": price_status, "notes": " ".join(notes),
        })
        upsert(report, f"t005:cost:hotel:{i}", CostLine, {
            "trip": trip, "stage": "actual", "ref": f"H{i - 2}", "category": "Hotels (lodging)",
            "description": f"{hotel}, {int(nights)} night(s) from {check_in:%d %b}", "supplier": supplier, "place": text(town),
            "unit_cost": money(rate), "units": Decimal(1), "times": Decimal(int(nights)), "basis": "per night",
            "currency": text(currency), "amount": money(total_orig), "fx_rate": fx, "amount_etb": total_etb,
            "who_pays": "Gadaa", "status": price_status, "hotel_booking": hb, "source_ref": where,
        })

    # Crew
    for role, rate, cat in (("Guide", guide_rate, "Guide daily fee"), ("Driver", driver_rate, "Driver")):
        crew = upsert(report, f"t005:crew:{role}", CrewAssignment, {
            "trip": trip, "role": role, "start_date": start, "end_date": end, "days": days, "daily_rate": rate,
            "notes": "Name not in the cost analysis.",
        })
        upsert(report, f"t005:cost:crew:{role}", CostLine, {
            "trip": trip, "stage": "actual", "ref": role[0], "category": cat, "description": f"{role} {days} days x {rate}",
            "unit_cost": rate, "units": Decimal(1), "times": Decimal(days), "basis": "per day", "amount": crew.total_fee,
            "amount_etb": crew.total_fee, "who_pays": "Gadaa", "crew_assignment": crew, "source_ref": f"{src} Summary inputs",
        })

    # Fuel
    fuel = fuel_cost(km, kmpl, fuel_price)
    upsert(report, "t005:cost:fuel", CostLine, {
        "trip": trip, "stage": "actual", "ref": "FUEL", "category": "Fuel",
        "description": f"Fuel: {km} km / {kmpl} km per litre x {fuel_price} ETB", "amount": fuel, "amount_etb": fuel,
        "basis": "per litre", "who_pays": "Gadaa", "receipt_status": "unknown", "source_ref": f"{src} Summary inputs",
        "attributes": {"route_km": str(km), "km_per_litre": str(kmpl), "price_per_litre": str(fuel_price),
                       "litres": str((km / kmpl).quantize(Decimal('0.01')))},
    })
    report.notes.append(f"Trip 005 fuel: the file keeps {inputs['Total route (km)']} / 7 x 183.49 unrounded "
                        f"(53,238.3128...); the app stores it to the cent: {fuel}.")

    # Ground costs
    ws = wb["Ground costs"]
    n = 0
    for i, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        ref, item, category, who, total = row[:5]
        if not ref or ref in ("Ref", "Total") or not isinstance(total, (int, float)):
            continue
        where = f"{src} Ground costs {ref} ({item})"
        place, _, desc = text(item).partition(":")
        status = "doubtful" if who == "Check" else "confirmed"
        if who == "Check":
            report.doubt(where, "marked 'Check': who pays is not confirmed")
        cat = T005_CATEGORY.get(text(category), text(category))
        upsert(report, f"t005:ground:{i}", CostLine, {
            "trip": trip, "stage": "actual", "ref": text(ref), "category": cat, "description": desc.strip() or text(item),
            "place": place.strip(), "amount": money(total), "amount_etb": money(total), "basis": "total for 2 people",
            "who_pays": text(who), "status": status, "source_ref": where,
            "attributes": {"source_category": text(category)} if cat != text(category) else {},
        })
        n += 1
    report.check("Trip 005 ground-cost lines", 62, n)

    trip.refresh_from_db()
    report.check("Trip 005 sales (ETB)", "1043946.90", trip.price_etb)
    report.check("Trip 005 total cost (ETB)", "614508.92", trip.cost_total_etb())
    report.check("Trip 005 profit (ETB)", "429437.98", trip.profit_etb())
    report.check("Trip 005 margin", "0.4114", trip.margin())
    return trip


# ---------------------------------------------------------------- Surma
def import_surma(path, report):
    wb = openpyxl.load_workbook(path, data_only=True)
    src = "Surma expense analysis"
    a = {text(r[0]): r[1] for r in wb["Assumptions"].iter_rows(min_row=1, values_only=True) if r[0]}
    eur_rate = money(a["EUR to ETB exchange rate (PROVISIONAL)"])
    price_eur = money(a["Total selling price, 2 guests (EUR)"])
    start, end = as_date(a["Guest trip start"]), as_date(a["Guest trip end"])
    trip = upsert(report, "trip:GAD-TOUR-001", Trip, {
        "code": "GAD-TOUR-001", "name": "Surma", "pax": int(a["Guests"]), "start_date": start, "end_date": end,
        "route": "Jimma, Mizan Teferi, Surma area (Kibish), Arba Minch", "route_family": "Surma / South-West",
        "status": "Completed", "price_amount": price_eur, "currency": "EUR", "fx_rate": eur_rate, "fx_confirmed": False,
        "notes": ("Price EUR 1,845 per person (1,785 programme + 60 single supplement) x 2. The EUR rate 184 is "
                  "PROVISIONAL. Suri village costs and other payments by Eric are still pending (see open items). "
                  "Crew: 4 (guide, cook, driver, Eric)."),
    }, lookup={"code": "GAD-TOUR-001"})
    report.doubt(src, f"EUR rate {eur_rate} is provisional; the trip price in ETB depends on it")
    report.doubt(src, "Partner not named in the file; left blank")

    ws = wb["Expenses"]
    head = [text(c.value) for c in ws[4]]
    col = {h: i for i, h in enumerate(head)}
    n_exp = 0
    for i, row in enumerate(ws.iter_rows(min_row=5, values_only=True), start=5):
        ref = text(row[col["ID"]])
        if not ref:
            continue
        where = f"{src} Expenses {ref}"
        source_cat = text(row[col["Category"]])
        amount_raw = row[col["Amount (ETB)"]]
        status_raw = text(row[col["Status"]])
        if ref.startswith("P"):
            upsert(report, f"surma:pending:{ref}", Task, {
                "title": f"Surma {ref}: price and document '{text(row[col['Vendor / payee']])}'",
                "trip": trip, "source_rule": "import: pending item", "source_key": f"surma:pending:{ref}",
                "notes": f"{text(row[col['Description']])} {text(row[col['Notes']])}".strip(),
            })
            report.doubt(where, "pending item with no amount: added as an open task, not as a cost")
            continue
        if ref.startswith("C"):
            continue  # crew handled below from the Crew Rates sheet
        amount = money(amount_raw)
        if amount is None:
            report.reject(where, f"no amount ({amount_raw!r})")
            continue
        recoverable = source_cat.startswith("Alcohol")
        excluded = status_raw == "Excluded"
        if source_cat == "Vehicle, Fuel & Local Transport":
            cat = "Fuel" if text(row[col["Vendor / payee"]]).startswith("Fuel") else "Boats and vehicle fees"
            if "Ride fee" in text(row[col["Description"]]):
                cat = "Airport transfers and taxis"
        else:
            cat = SURMA_CATEGORY.get(source_cat)
        if cat is None:
            report.reject(where, f"unknown category '{source_cat}'")
            continue
        currency, fx, orig = "ETB", Decimal("1"), amount
        if source_cat == "Domestic Flights":
            currency, fx, orig = "EUR", eur_rate, Decimal("387.00")
        documentation = text(row[col["Documentation"]])
        flag = text(row[col["Flag"]])
        exp = upsert(report, f"surma:expense:{ref}", Expense, {
            "ref": ref, "trip": trip, "date": as_date(row[col["Date"]]), "category": cat,
            "description": text(row[col["Description"]]) if not text(row[col["Vendor / payee"]]).startswith(("Fuel", "Domestic")) else f"{text(row[col['Vendor / payee']])}: {text(row[col['Description']])}",
            "vendor": text(row[col["Vendor / payee"]]), "location": text(row[col["Location"]]),
            "currency": currency, "amount": orig, "fx_rate": fx, "fx_confirmed": currency == "ETB", "amount_etb": amount,
            "receipt_type": documentation, "receipt_status": "yes" if documentation in DOCUMENTED else "no",
            "reference": text(row[col["Reference"]]), "status": "excluded" if excluded else "included",
            "recoverable": recoverable, "flag": flag, "notes": text(row[col["Notes"]]),
        })
        upsert(report, f"surma:cost:{ref}", CostLine, {
            "trip": trip, "stage": "actual", "ref": ref, "category": cat, "description": exp.description[:400],
            "place": exp.location, "currency": currency, "amount": orig, "fx_rate": fx, "amount_etb": amount,
            "who_pays": "Gadaa", "status": "doubtful" if flag.lower().startswith("uncertain") else "confirmed",
            "receipt_status": exp.receipt_status, "recoverable": recoverable, "excluded": excluded, "expense": exp,
            "source_ref": where, "attributes": {"source_category": source_cat},
        })
        if flag.lower().startswith("uncertain"):
            report.doubt(where, flag)
        n_exp += 1
    report.check("Surma expense lines E01-E36", 36, n_exp)

    roles = {"French-speaking guide": ("Guide", "Guide daily fee"), "Cook": ("Cook", "Cook"),
             "Driver": ("Driver", "Driver"), "General Manager": ("Other", "Driver")}
    for i, row in enumerate(wb["Crew Rates"].iter_rows(min_row=4, values_only=True), start=4):
        role_raw, person, rate = text(row[0]), text(row[1]), row[2]
        if role_raw not in roles:
            continue
        role, cat = roles[role_raw]
        where = f"{src} Crew Rates row {i} ({role_raw})"
        has_rate = isinstance(rate, (int, float)) and rate > 0
        crew = upsert(report, f"surma:crew:{role_raw}", CrewAssignment, {
            "trip": trip, "role": role if role != "Other" else "Other", "name": "" if person == "Not named" else person,
            "start_date": as_date(row[3]), "end_date": as_date(row[4]), "days": int(row[5]) if has_rate else None,
            "daily_rate": money(rate) if has_rate else None, "rate_status": "confirmed" if has_rate else "pending",
            "notes": text(row[8]),
        })
        if not has_rate:
            upsert(report, f"surma:task:rate:{person}", Task, {
                "title": f"Agree a written daily rate with {person} before the next trip", "trip": trip,
                "source_rule": "import: missing rate", "source_key": f"surma:task:rate:{person}",
            })
            report.doubt(where, f"{person} has no daily rate; crew record kept, no cost, open task added")
            continue
        upsert(report, f"surma:cost:crew:{role_raw}", CostLine, {
            "trip": trip, "stage": "actual", "ref": {"Guide": "C01", "Cook": "C02", "Driver": "C03"}[role],
            "category": cat, "description": f"{role_raw} {crew.days} days x {crew.daily_rate}", "unit_cost": crew.daily_rate,
            "units": Decimal(1), "times": Decimal(crew.days), "basis": "per day", "amount": crew.total_fee,
            "amount_etb": crew.total_fee, "who_pays": "Gadaa", "crew_assignment": crew, "source_ref": where,
            "attributes": {"source_category": "Crew Daily Rates"},
        })

    trip.refresh_from_db()
    report.check("Surma gross recorded cost (ETB)", "498473.78", trip.cost_total_etb())
    report.check("Surma recoverable alcohol (ETB)", "2160.00", trip.recoverable_etb())
    report.check("Surma net cost (ETB)", "496313.78", trip.net_cost_etb())
    report.check("Surma price (ETB, provisional rate)", "678960.00", trip.price_etb)
    report.check("Surma profit before pending costs (ETB)", "182646.22", trip.profit_etb())
    report.check("Surma margin", "0.2690", trip.margin())
    report.notes.append("Surma categories were mapped to the workbook's cost categories; the original category is kept on each line. "
                        "Groceries and restaurant meals both became 'Client meals', camp supplies and alcohol became 'Other'.")
    return trip


# ---------------------------------------------------------------- hotel bookings sheet
def import_bookings(path, report, trip_dates=None):
    """Trips 3 and 4 from the bookings sheet. Trip 5 rows are only compared, because Trip 005 comes from its cost analysis."""
    wb = openpyxl.load_workbook(path, data_only=True)
    src = "Hotel bookings Nov 2026"
    ws = wb["Bookings"]
    head = [text(c.value) for c in ws[4]]
    col = {h: i for i, h in enumerate(head)}
    rows = []
    for i, row in enumerate(ws.iter_rows(min_row=5, values_only=True), start=5):
        if not row[col["Hotel"]]:
            continue
        rows.append((i, row))

    trips = {}
    for i, row in rows:
        num = row[col["GADTOUR number"]]
        if num in (3, 4):
            trips.setdefault(int(num), []).append(row)
    for num, trip_rows in sorted(trips.items()):
        code = f"GAD-TOUR-{num:03d}"
        start = min(as_date(r[col["Check-in"]]) for r in trip_rows)
        end = max(as_date(r[col["Check-out"]]) for r in trip_rows)
        upsert(report, f"trip:{code}", Trip, {
            "code": code, "name": "", "pax": 1, "start_date": start, "end_date": end, "status": "Confirmed",
            "currency": "EUR", "notes": "Created from the November 2026 hotel bookings sheet only. Price, guests and route to be filled in.",
        }, lookup={"code": code})
        report.doubt(f"{src} {code}", "trip created from hotel rows only: dates are first check-in to last check-out; "
                                      "guests set to 1 from the room type; price, partner and route empty")

    for i, row in rows:
        where = f"{src} row {i} ({text(row[col['Hotel']])}, {as_date(row[col['Check-in']]):%d %b})"
        num, status = row[col["GADTOUR number"]], text(row[col["Status"]])
        if num is None:
            report.reject(where, f"no trip number (status {status})")
            continue
        if num == 5:
            continue
        if num not in (3, 4):
            report.reject(where, f"trip number {num} not expected")
            continue
        trip = Trip.objects.get(code=f"GAD-TOUR-{int(num):03d}")
        currency = text(row[col["Currency"]]) or ""
        rate = money(row[col["Price / night (used)"]])
        total_etb_raw = row[col["Total (ETB)"]]
        total_etb = money(total_etb_raw) if isinstance(total_etb_raw, (int, float)) else None
        price_status, notes = "confirmed", [text(row[col["Notes"]])]
        if rate is None:
            price_status = "doubtful"
            report.doubt(where, "no price in the sheet")
        elif currency != "ETB":
            price_status = "unconfirmed"
            report.doubt(where, f"{rate} {currency or 'no currency'} a night, no exchange rate set, so no ETB total")
        if text(row[col["Payment"]]) == "To check":
            notes.append("Payment: to check.")
        hotel = text(row[col["Hotel"]])
        if " or " in hotel:
            report.doubt(where, f"'{hotel}': lodge not decided")
        supplier = _supplier_for(text(row[col["Town"]]), hotel)
        nights = int(row[col["Nights"]])
        hb = upsert(report, f"bookings:{i}", HotelBooking, {
            "trip": trip, "supplier": supplier, "hotel_name": hotel, "town": text(row[col["Town"]]),
            "check_in": as_date(row[col["Check-in"]]), "check_out": as_date(row[col["Check-out"]]),
            "room_description": text(row[col["Room"]]), "rate_per_night": rate, "currency": currency or "ETB",
            "fx_rate": Decimal("1"), "total_amount": to_cents(rate * nights) if rate is not None else None,
            "total_etb": total_etb, "status": status, "payment_details": text(row[col["Account number"]]),
            "price_status": price_status, "notes": " ".join(n for n in notes if n) + f" Contact log: {text(row[col['Contact log']])}".rstrip(": "),
        })
        if total_etb is not None:
            upsert(report, f"bookings:cost:{i}", CostLine, {
                "trip": trip, "stage": "actual", "ref": f"HB{i}", "category": "Hotels (lodging)",
                "description": f"{hotel}, {nights} night(s) from {hb.check_in:%d %b}", "supplier": supplier,
                "place": hb.town, "unit_cost": rate, "units": Decimal(1), "times": Decimal(nights), "basis": "per night",
                "amount": total_etb, "amount_etb": total_etb, "who_pays": "Gadaa", "hotel_booking": hb, "source_ref": where,
            })
    report.notes.append("Bookings sheet: Trip 5 rows were compared, not imported (Trip 005 comes from its cost analysis). "
                        "Cancelled rows without a trip number are listed as rejected.")


def import_hotel_contacts(path, report):
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Hotel contacts"]
    for i, row in enumerate(ws.iter_rows(min_row=4, values_only=True), start=4):
        hotel, town, phone, email, notes = (text(v) for v in row[:5])
        if not hotel or hotel == "Hotel":
            continue
        supplier = _supplier_for(town, hotel)
        where = f"Hotel contacts row {i} ({hotel})"
        if "undefined" in notes or "country code" in notes:
            report.doubt(where, "phone numbers lack the country code")
        if supplier is None:
            supplier = Supplier.objects.filter(name=hotel).first()
        if supplier is None:
            numbers = [int(c.split("-")[1]) for c in Supplier.objects.filter(code__startswith="S-").values_list("code", flat=True) if c.split("-")[1].isdigit()]
            code = f"S-{(max(numbers) + 1 if numbers else 1):03d}"
            existing = upsert(report, f"contacts:supplier:{hotel}", Supplier, {
                "code": code, "name": hotel, "town": town, "category": "Hotel", "phone": phone, "email": email,
                "notes": f"From the hotel contacts sheet. {notes}".strip(),
            }, lookup={"name": hotel})
            continue
        changed = False
        if phone and not supplier.phone:
            supplier.phone, changed = phone, True
        if email and not supplier.email:
            supplier.email, changed = email, True
        if changed:
            supplier.save()
            report.updated += 1
        if "Number was in the price column" in notes:
            report.doubt(where, "phone number came from the price column of the original sheet")
