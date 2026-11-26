"""Business rules taken from the workbook and agreements. Each is tested."""
from datetime import timedelta
from decimal import Decimal, ROUND_CEILING, ROUND_HALF_UP

CENT = Decimal("0.01")


def add_business_days(start, days, weekend=(6,)):
    """
    Same as Excel WORKDAY.INTL(start, days, 11): count forward `days` working
    days, skipping Sundays (weekday 6). Public holidays are not known yet
    (OPEN_QUESTIONS.md), so they are not skipped.
    """
    current = start
    remaining = days
    while remaining > 0:
        current += timedelta(days=1)
        if current.weekday() not in weekend:
            remaining -= 1
    return current


def crew_payment_schedule(days, daily_rate, advance_pct, end_date, balance_business_days=7):
    """Total fee, 40% advance, 60% balance and the balance due date."""
    if not days or daily_rate is None:
        return None, None, None, add_business_days(end_date, balance_business_days) if end_date else None
    total = (Decimal(days) * Decimal(daily_rate)).quantize(CENT, rounding=ROUND_HALF_UP)
    advance = (total * Decimal(advance_pct)).quantize(CENT, rounding=ROUND_HALF_UP)
    balance = total - advance
    due = add_business_days(end_date, balance_business_days) if end_date else None
    return total, advance, balance, due


def fuel_cost(route_km, km_per_litre, price_per_litre, detour_pct=Decimal("0")):
    """km x (1 + detour) / km per litre x price, rounded to the cent."""
    km = Decimal(route_km) * (1 + Decimal(detour_pct))
    litres = km / Decimal(km_per_litre)
    return (litres * Decimal(price_per_litre)).quantize(CENT, rounding=ROUND_HALF_UP)


def quote_price(direct_cost, contingency_pct, margin, vat_rate, claims_input_vat, charges_output_vat,
                vat_inclusive_cost, expected_rate, fx_buffer, pax, round_to=5):
    """
    The Trip Costing sheet, step by step. Returns a dict so every number can
    be traced. Amounts in ETB unless named per client currency.
    """
    direct_cost = Decimal(direct_cost)
    contingency = direct_cost * Decimal(contingency_pct)
    total_cost = direct_cost + contingency
    vat_rate = Decimal(vat_rate)
    input_vat = Decimal("0")
    if claims_input_vat:
        input_vat = Decimal(vat_inclusive_cost) * (1 + Decimal(contingency_pct)) * vat_rate / (1 + vat_rate)
    net_cost = total_cost - input_vat
    price_before_vat = net_cost / (1 - Decimal(margin))
    output_vat = price_before_vat * vat_rate if charges_output_vat else Decimal("0")
    price_incl_vat = price_before_vat + output_vat
    safe_rate = Decimal(expected_rate) * (1 - Decimal(fx_buffer))
    per_person = (price_incl_vat / safe_rate / pax / round_to).to_integral_value(rounding=ROUND_CEILING) * round_to
    total_quoted = per_person * pax
    quoted_etb = total_quoted * Decimal(expected_rate)
    vat_in_quote = quoted_etb * vat_rate / (1 + vat_rate) if charges_output_vat else Decimal("0")
    net_revenue = quoted_etb - vat_in_quote
    profit = net_revenue - net_cost
    return {
        "contingency": contingency,
        "total_cost": total_cost,
        "input_vat": input_vat,
        "net_cost": net_cost,
        "price_before_vat": price_before_vat,
        "output_vat": output_vat,
        "price_incl_vat": price_incl_vat,
        "safe_rate": safe_rate,
        "price_per_person": per_person,
        "total_quoted": total_quoted,
        "quoted_etb": quoted_etb,
        "net_revenue": net_revenue,
        "profit": profit,
        "margin": profit / net_revenue if net_revenue else Decimal("0"),
        "markup": profit / net_cost if net_cost else Decimal("0"),
    }


def margin_on_price(price, cost):
    return (Decimal(price) - Decimal(cost)) / Decimal(price)


def markup_on_cost(price, cost):
    return (Decimal(price) - Decimal(cost)) / Decimal(cost)
