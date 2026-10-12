import csv
import math
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

from django.conf import settings

from .models import Inventory, Product


DATA_DIR = Path(settings.DATA_DIR)
FORECAST_FILE = Path(settings.BASE_DIR) / "ml" / "forecast.csv"


def load_lead_times():
    result = {}
    with (DATA_DIR / "lead_times.csv").open(
        newline="", encoding="utf-8-sig"
    ) as f:
        for row in csv.reader(f):
            if len(row) < 2 or row[0].strip().lower() == "sku":
                continue
            sku = row[0].strip()
            try:
                weeks = int(row[1])
            except ValueError:
                continue
            if weeks > 0:
                result[sku] = weeks
    return result


def load_forecasts():
    forecasts = defaultdict(list)
    with FORECAST_FILE.open(
        newline="", encoding="utf-8-sig"
    ) as f:
        for row in csv.DictReader(f):
            sku = row["sku"].strip()
            week = date.fromisoformat(row["week_start"].strip())
            units = float(row["forecast_units"])
            if not math.isfinite(units) or units < 0:
                raise ValueError(f"Invalid forecast for {sku}")
            forecasts[sku].append((week, units))

    for sku in forecasts:
        forecasts[sku].sort(key=lambda item: item[0])

    return forecasts


def load_recent_sales():
    sales = defaultdict(list)
    with (DATA_DIR / "sales_history.csv").open(
        newline="", encoding="utf-8-sig"
    ) as f:
        for row in csv.DictReader(f):
            sku = row["sku"].strip()
            week = date.fromisoformat(row["week_start"].strip())
            units = float(row["units_sold"])
            sales[sku].append((week, units))

    for sku in sales:
        sales[sku].sort(key=lambda item: item[0])

    return sales


def forecast_for_sku(sku, forecasts):
    rows = forecasts.get(sku)
    if not rows:
        return None

    return [
        {
            "week_start": week.isoformat(),
            "forecast_units": round(units, 2),
        }
        for week, units in rows
    ]


def reorder_suggestions():
    lead_times = load_lead_times()
    forecasts = load_forecasts()
    sales = load_recent_sales()

    # Query live inventory every time this function is called.
    inventory_rows = Inventory.objects.select_related("product").all()
    live_stock = {
        row.product_id: row.quantity
        for row in inventory_rows
    }
    active_skus = set(
        Product.objects.filter(is_active=True).values_list("sku", flat=True)
    )

    results = []

    for sku in sorted(lead_times):
        if sku not in forecasts or sku not in active_skus:
            continue

        L = lead_times[sku]
        weekly_forecasts = forecasts[sku]

        if len(weekly_forecasts) < L:
            continue

        lead_time_demand = sum(
            units for _, units in weekly_forecasts[:L]
        )

        recent_units = [
            units for _, units in sales.get(sku, [])[-12:]
        ]
        sigma = (
            statistics.stdev(recent_units)
            if len(recent_units) >= 2
            else 0.0
        )

        safety_stock = math.ceil(1.65 * sigma * math.sqrt(L))
        reorder_point = lead_time_demand + safety_stock
        current_stock = live_stock.get(sku, 0)
        reorder_qty = max(
            0, math.ceil(reorder_point - current_stock)
        )

        results.append({
            "sku": sku,
            "current_stock": current_stock,
            "lead_time_weeks": L,
            "lead_time_demand": round(lead_time_demand, 2),
            "safety_stock": safety_stock,
            "reorder_point": round(reorder_point, 2),
            "reorder_qty": reorder_qty,
        })

    return results
