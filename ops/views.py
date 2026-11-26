from django.shortcuts import get_object_or_404, render

from core import roles
from ops.models import Trip


def trip_detail(request, pk):
    roles.require(roles.can_view, request.user)
    trip = get_object_or_404(Trip, pk=pk)
    lines = trip.cost_lines.filter(stage="actual")
    by_cat = {}
    for line in lines.filter(excluded=False):
        by_cat.setdefault(line.category, 0)
        by_cat[line.category] += line.amount_etb or 0
    total = trip.cost_total_etb()
    categories = sorted(((c, v, (v / total * 100) if total else 0) for c, v in by_cat.items()), key=lambda x: -x[1])
    ctx = {
        "trip": trip,
        "categories": categories,
        "cost_total": total,
        "recoverable": trip.recoverable_etb(),
        "net_cost": trip.net_cost_etb(),
        "profit": trip.profit_etb(),
        "margin": (trip.margin() * 100) if trip.margin() is not None else None,
        "received": trip.received_etb(),
        "hotels": trip.hotel_bookings.all(),
        "crew": trip.crew.all(),
        "expenses": trip.expenses.all(),
        "lines": lines,
        "payments": trip.payments.all(),
        "passenger_count": trip.passengers.count(),
        "tasks": trip.tasks.all(),
    }
    return render(request, "ops/trip_detail.html", ctx)
