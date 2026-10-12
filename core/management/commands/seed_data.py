
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Dealer, Inventory, Product


class Command(BaseCommand):
    help = "Import catalogue and dealer CSV files safely and repeatably."

    def add_arguments(self, parser):
        parser.add_argument(
            "--data-dir",
            type=str,
            default=None,
            help="Directory containing catalogue.csv and dealers.csv.",
        )

    def handle(self, *args, **options):
        data_dir = Path(options["data_dir"] or settings.DATA_DIR)

        if not data_dir.is_dir():
            raise CommandError(f"Data directory does not exist: {data_dir}")

        catalogue_path = data_dir / "catalogue.csv"
        dealers_path = data_dir / "dealers.csv"

        for path in (catalogue_path, dealers_path):
            if not path.is_file():
                raise CommandError(f"Required CSV file not found: {path}")

        try:
            with transaction.atomic():
                products_created, products_updated = self.import_products(
                    catalogue_path
                )
                dealers_created, dealers_updated = self.import_dealers(
                    dealers_path
                )
        except (ValueError, InvalidOperation, KeyError) as exc:
            raise CommandError(
                f"Import failed; database changes were rolled back: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                "Import complete. "
                f"Products created: {products_created}, "
                f"products updated: {products_updated}, "
                f"dealers created: {dealers_created}, "
                f"dealers updated: {dealers_updated}."
            )
        )

    def read_csv(self, path):
        with path.open("r", encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)

            if not reader.fieldnames:
                raise ValueError(f"{path.name} is empty or has no header")

            headers = {
                header.strip() for header in reader.fieldnames if header
            }

            return list(reader), headers

    def import_products(self, path):
        rows, headers = self.read_csv(path)

        required = {
            "sku",
            "name",
            "category",
            "brand",
            "vehicle_fitment",
            "price",
            "stock",
            "description",
        }

        missing = required - headers
        if missing:
            raise ValueError(
                f"{path.name} is missing columns: {', '.join(sorted(missing))}"
            )

        created = 0
        updated = 0

        for line_number, row in enumerate(rows, start=2):
            row = {
                key.strip(): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }

            sku = row.get("sku", "")
            name = row.get("name", "")

            if not sku or not name:
                raise ValueError(
                    f"{path.name}, line {line_number}: SKU and name are required"
                )

            try:
                price = Decimal(row.get("price", ""))
                stock = int(row.get("stock", ""))
            except (InvalidOperation, ValueError) as exc:
                raise ValueError(
                    f"{path.name}, line {line_number}: invalid price or stock"
                ) from exc

            if not price.is_finite() or price < 0:
                raise ValueError(
                    f"{path.name}, line {line_number}: price must be non-negative"
                )

            if stock < 0:
                raise ValueError(
                    f"{path.name}, line {line_number}: stock cannot be negative"
                )

            defaults = {
                "name": name,
                "category": row.get("category", ""),
                "brand": row.get("brand", ""),
                "description": row.get("description", ""),
                "unit_price": price,
                "gst_rate": Decimal("18.00"),
                "is_active": True,
                "vehicle_fitment": row.get("vehicle_fitment", ""),
            }

            product, was_created = Product.objects.update_or_create(
                sku=sku,
                defaults=defaults,
            )

            if was_created:
                created += 1
            else:
                updated += 1

            # Only initialize stock for new inventory records.
            # Re-running the seed command will not overwrite stock
            # that has subsequently changed through the API.
            Inventory.objects.get_or_create(
                product=product,
                defaults={"quantity": stock},
            )

        return created, updated

    def import_dealers(self, path):
        rows, headers = self.read_csv(path)

        required = {
            "dealer_code",
            "name",
            "city",
            "phone",
            "email",
            "gstin",
            "credit_limit",
        }

        missing = required - headers
        if missing:
            raise ValueError(
                f"{path.name} is missing columns: {', '.join(sorted(missing))}"
            )

        created = 0
        updated = 0

        for line_number, row in enumerate(rows, start=2):
            row = {
                key.strip(): (value or "").strip()
                for key, value in row.items()
                if key is not None
            }

            code = row.get("dealer_code", "")
            name = row.get("name", "")
            city = row.get("city", "")

            if not code or not name or not city:
                raise ValueError(
                    f"{path.name}, line {line_number}: "
                    "dealer_code, name, and city are required"
                )

            try:
                credit_limit = Decimal(row.get("credit_limit", ""))
            except InvalidOperation as exc:
                raise ValueError(
                    f"{path.name}, line {line_number}: invalid credit_limit"
                ) from exc

            if not credit_limit.is_finite() or credit_limit < 0:
                raise ValueError(
                    f"{path.name}, line {line_number}: "
                    "credit_limit must be non-negative"
                )

            defaults = {
                "name": name,
                "city": city,
                "phone": row.get("phone", ""),
                "email": row.get("email", ""),
                "gstin": row.get("gstin", ""),
                "credit_limit": credit_limit,
            }

            _, was_created = Dealer.objects.update_or_create(
                dealer_code=code,
                defaults=defaults,
            )

            if was_created:
                created += 1
            else:
                updated += 1

        return created, updated
