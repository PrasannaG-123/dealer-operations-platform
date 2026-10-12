import csv
import statistics
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "VIKMO DealerDesk Assignment" / "data"
LEAD_FILE = DATA / "lead_times.csv"
SALES_FILE = DATA / "sales_history.csv"
OUT_FILE = ROOT / "ml" / "forecast.csv"

lead_skus = []
with LEAD_FILE.open(newline="", encoding="utf-8-sig") as f:
    for row in csv.reader(f):
        if len(row) >= 2 and row[0].strip().lower() != "sku":
            lead_skus.append(row[0].strip())

sales = defaultdict(list)
with SALES_FILE.open(newline="", encoding="utf-8-sig") as f:
    for row in csv.DictReader(f):
        sku = row["sku"].strip()
        week = date.fromisoformat(row["week_start"].strip())
        units = float(row["units_sold"])
        sales[sku].append((week, units))

weeks = [
    date(2026, 9, 28),
    date(2026, 10, 5),
    date(2026, 10, 12),
    date(2026, 10, 19),
]

OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
with OUT_FILE.open("w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(["sku", "week_start", "forecast_units"])
    for sku in lead_skus:
        history = sorted(sales.get(sku, []), key=lambda x: x[0])
        recent = [units for _, units in history[-12:]]
        forecast = max(0.0, statistics.mean(recent)) if recent else 0.0
        for week in weeks:
            writer.writerow([sku, week.isoformat(), f"{forecast:.2f}"])

print(f"Wrote {OUT_FILE}")
print(f"SKUs: {len(lead_skus)}; forecast rows: {len(lead_skus) * 4}")
