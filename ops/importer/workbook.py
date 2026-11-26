"""Import from 01_GADAA_Operations_Workbook.xlsx: Settings, Lists, Suppliers, Fees Reference."""
import re

import openpyxl

from core.models import AppSetting, Choice
from ops.importer.base import as_date, dec, money, text, upsert
from ops.models import FeeReference, Supplier, SupplierRate

# Settings sheet label -> (key, kind, confirmed). Confirmed only where the
# source names a contract or the letterhead; everything else is an assumption.
SETTINGS = {
    "Company name": ("company_name", "text", True),
    "Company TIN": ("company_tin", "text", True),
    "VAT rate": ("vat_rate", "percent", False),
    "Company is VAT-registered and claims input VAT? (Yes/No)": ("claims_input_vat", "yesno", False),
    "Charge output VAT on client packages? (Yes/No)": ("charges_output_vat", "yesno", False),
    "Default target margin (% of selling price)": ("target_margin", "percent", False),
    "Contingency (% added to direct cost)": ("contingency_pct", "percent", False),
    "FX safety buffer (% off the exchange rate)": ("fx_buffer", "percent", False),
    "EUR to ETB rate (ETB per 1 EUR)": ("eur_etb", "decimal", False),
    "USD to ETB rate (ETB per 1 USD)": ("usd_etb", "decimal", False),
    "Fuel price (ETB per litre)": ("fuel_price", "decimal", False),
    "Car consumption (km per litre)": ("km_per_litre", "decimal", False),
    "Client deposit (% of total price)": ("deposit_pct", "percent", False),
    "Client balance due (days before arrival)": ("balance_days_before", "int", False),
    "Crew advance (% paid on departure day)": ("crew_advance_pct", "percent", True),
    "Crew balance due (business days after trip, Sundays excluded)": ("crew_balance_days", "int", True),
    "Max guide hotel room per night (ETB)": ("max_guide_room", "decimal", True),
    "Max single expense without receipt (ETB)": ("max_single_no_receipt", "decimal", True),
    "Max total expenses without receipt per trip (ETB)": ("max_total_no_receipt", "decimal", True),
    "Quote validity (days)": ("quote_validity_days", "int", False),
    "Follow-up reminder after quote sent (days)": ("followup_days", "int", False),
}


def import_settings(wb, report, src):
    ws = wb["Settings"]
    seen = 0
    for row in range(4, ws.max_row + 1):
        label, value, note = (ws.cell(row, c).value for c in (1, 2, 3))
        if not label:
            continue
        where = f"{src} Settings row {row}"
        if label not in SETTINGS:
            report.reject(where, f"unknown setting '{label}'")
            continue
        key, kind, confirmed = SETTINGS[label]
        if value is None:
            report.reject(where, f"'{label}' has no value")
            continue
        number = dec(value) if kind in ("percent", "decimal", "int") else None
        if number is None:
            stored = text(value)
        elif kind == "int":
            stored = str(int(number))
        else:
            stored = format(number.normalize(), "f")
        upsert(report, f"workbook:settings:{key}", AppSetting,
               {"key": key, "label": label, "kind": kind, "value": stored, "source_note": text(note), "confirmed": confirmed},
               lookup={"key": key})
        if not confirmed:
            report.doubt(where, f"{label} = {stored} imported as unconfirmed")
        seen += 1
    # The SOP adds a second follow-up at +7 days (Phase 1 rule); keep it visible as a setting.
    report.notes.append(f"{seen} settings imported. The second quote follow-up (+7 days) comes from the SOP, not the workbook, and is added in Phase 1.")


def import_lists(wb, report, src):
    ws = wb["Lists"]
    for col in range(1, ws.max_column + 1):
        list_name = text(ws.cell(1, col).value)
        if not list_name:
            continue
        order = 0
        for row in range(2, 24):
            value = text(ws.cell(row, col).value)
            if not value:
                continue
            order += 1
            upsert(report, f"workbook:lists:{list_name}:{value}", Choice,
                   {"list_name": list_name, "value": value, "order": order},
                   lookup={"list_name": list_name, "value": value})


MULTI = re.compile(r"\s/\s|\sor\s", re.I)


def import_suppliers(wb, report, src):
    ws = wb["Suppliers"]
    cols = [text(ws.cell(4, c).value) for c in range(1, ws.max_column + 1)]
    idx = {name: i for i, name in enumerate(cols)}
    for row in ws.iter_rows(min_row=5, values_only=True):
        code = text(row[idx["ID"]])
        if not code:
            continue
        where = f"{src} Suppliers {code}"
        name = text(row[idx["Supplier name"]])
        if not name:
            report.reject(where, "no supplier name")
            continue
        needs_review = bool(MULTI.search(name))
        values = {
            "code": code, "name": name, "town": text(row[idx["Destination"]]), "category": text(row[idx["Category"]]),
            "contact_person": text(row[idx["Contact person"]]), "phone": text(row[idx["Phone / WhatsApp"]]),
            "email": text(row[idx["Email"]]), "meal_plan": text(row[idx["Meal plan"]]),
            "foc_policy": text(row[idx["FOC policy (guide / driver room)"]]),
            "payment_terms": text(row[idx["Payment terms"]]), "cancellation_terms": text(row[idx["Cancellation terms"]]),
            "rating": int(row[idx["Rating (1-5)"]]) if row[idx["Rating (1-5)"]] else None,
            "last_used": as_date(row[idx["Last used (date)"]]),
            "needs_review": needs_review, "notes": text(row[idx["Notes"]]),
        }
        supplier = upsert(report, f"workbook:suppliers:{code}", Supplier, values, lookup={"code": code})
        if needs_review:
            report.doubt(where, f"'{name}' names more than one place; split it into one supplier per lodge")
        ref_rate = money(row[idx["Reference rate paid last trip (per room-night)"]])
        currency = text(row[idx["Rate currency"]])
        if ref_rate is not None:
            if not currency:
                report.doubt(where, "reference rate has no currency; not imported as a rate")
                continue
            upsert(report, f"workbook:suppliers:{code}:refrate", SupplierRate, {
                "supplier": supplier, "item": "Room-night (paid on a past trip)", "amount": ref_rate,
                "currency": currency, "basis": "per room-night", "kind": "paid",
                "source_note": "Workbook Suppliers sheet, 'reference rate paid last trip'. Not a contracted net rate.",
            })
        for label, item in (("Net rate SGL", "SGL room"), ("Net rate DBL", "DBL room"), ("Net rate TWN", "TWN room")):
            amount = money(row[idx[label]])
            if amount is not None:
                upsert(report, f"workbook:suppliers:{code}:{item}", SupplierRate, {
                    "supplier": supplier, "item": item, "amount": amount, "currency": currency or "ETB",
                    "basis": "per room-night", "kind": "contracted",
                    "valid_from": as_date(row[idx["Rates valid from"]]), "valid_to": as_date(row[idx["Rates valid to"]]),
                })


def import_fees(wb, report, src):
    ws = wb["Fees Reference"]
    for row in range(5, ws.max_row + 1):
        place, item, price, basis, source, verify = (ws.cell(row, c).value for c in range(1, 7))
        if not place and not item:
            continue
        where = f"{src} Fees Reference row {row} ({text(place)}: {text(item)})"
        amount = money(price)
        if amount is None:
            report.reject(where, "no price")
            continue
        doubtful = "*" in text(basis) or bool(re.search(r"confirm|check|not in", text(verify), re.I))
        upsert(report, f"workbook:fees:{row}", FeeReference, {
            "place": text(place), "item": text(item), "price_etb": amount, "basis": text(basis),
            "source": text(source), "verify_note": text(verify), "status": "doubtful" if doubtful else "unconfirmed",
        })
        if doubtful:
            report.doubt(where, f"basis or price to confirm ({text(basis)} {text(verify)})".strip())


def run(path, report):
    wb = openpyxl.load_workbook(path, data_only=False)
    src = "Workbook"
    import_settings(wb, report, src)
    import_lists(wb, report, src)
    import_suppliers(wb, report, src)
    import_fees(wb, report, src)
    for sheet in ("Inquiries", "Trips", "Hotel Bookings", "Rooming & Manifest", "Crew Payments", "Payments", "Expenses"):
        ws = wb[sheet]
        typed = sum(1 for r in ws.iter_rows(min_row=6, values_only=True)
                    if any(v is not None and not (isinstance(v, str) and v.startswith("=")) for v in r))
        if typed:
            report.doubt(f"{src} {sheet}", f"{typed} typed rows found but this sheet is not mapped yet")
    report.notes.append("Workbook sheets Inquiries, Trips, Hotel Bookings, Rooming & Manifest, Crew Payments, Payments and Expenses hold only example rows; skipped.")
