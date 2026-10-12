
import os
import time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import requests
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import Product, Inventory


MAX_ATTEMPTS = 5
PAGE_SIZE = 20


def _backoff(attempt):
    """Short exponential backoff between retry attempts."""
    time.sleep(min(0.5 * (2 ** attempt), 4))


def _supplier_get(session, url, headers, params, counters):
    """
    Fetch one supplier page.

    Retries connection failures, HTTP 429, and HTTP 5xx responses.
    Authentication and other HTTP 4xx errors fail immediately.
    Counts every actual HTTP request, including retries.
    """
    last_error = None

    for attempt in range(MAX_ATTEMPTS):
        try:
            counters["requests_made"] += 1
            response = session.get(
                url,
                headers=headers,
                params=params,
                timeout=10,
            )
        except requests.RequestException as exc:
            last_error = exc

            if attempt < MAX_ATTEMPTS - 1:
                _backoff(attempt)
                continue

            break

        if response.status_code == 429 or response.status_code >= 500:
            last_error = RuntimeError(
                f"Supplier returned HTTP {response.status_code}"
            )

            if attempt < MAX_ATTEMPTS - 1:
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After", "1")
                    try:
                        delay = min(max(float(retry_after), 0), 4)
                    except (ValueError, TypeError):
                        delay = 1
                    time.sleep(delay)
                else:
                    _backoff(attempt)

                continue

            break

        # Non-retriable HTTP errors, including rejected API keys,
        # propagate to the caller without unnecessary retries.
        response.raise_for_status()
        return response

    raise RuntimeError(
        f"Supplier request failed after retries: {last_error}"
    )


def _error_response(code, message, status=502, details=None):
    return JsonResponse(
        {
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
            }
        },
        status=status,
    )


def _reject(rejected, sku, reason):
    rejected.append({
        "sku": str(sku or ""),
        "reason": reason,
    })


def _parse_supplier_item(raw_item, rejected):
    """Validate one item and return normalized data or None."""
    if not isinstance(raw_item, dict):
        _reject(rejected, "", "Item must be an object")
        return None

    item = dict(raw_item)
    sku = item.get("sku")

    if not isinstance(sku, str) or not sku.strip():
        _reject(rejected, sku, "SKU is missing or invalid")
        return None

    sku = sku.strip()
    price_raw = item.get("price")

    try:
        price = Decimal(str(price_raw))
    except (InvalidOperation, TypeError, ValueError):
        _reject(rejected, sku, "Price is missing or invalid")
        return None

    if not price.is_finite() or price <= 0:
        _reject(rejected, sku, "Price must be a positive finite number")
        return None

    if price.as_tuple().exponent < -2:
        _reject(rejected, sku, "Price must have at most two decimal places")
        return None

    try:
        price = price.quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except InvalidOperation:
        _reject(rejected, sku, "Price is outside the supported range")
        return None

    item["sku"] = sku
    item["_parsed_price"] = price
    return item


def _supplier_error(exc):
    """Return a safe, consistent supplier failure response."""
    if isinstance(exc, requests.HTTPError):
        response = exc.response
        status_code = response.status_code if response is not None else None

        if status_code in (401, 403):
            message = "Supplier API key was rejected."
        else:
            message = f"Supplier returned an unsuccessful HTTP response ({status_code})."
    else:
        message = f"Supplier sync failed: {exc}"

    return _error_response(
        "SUPPLIER_UNAVAILABLE",
        message,
        status=502,
    )


@csrf_exempt
@require_POST
def sync_supplier(request):
    base_url = os.environ.get("SUPPLIER_API_URL", "").rstrip("/")
    api_key = os.environ.get("SUPPLIER_API_KEY", "")

    if not base_url or not api_key:
        return _error_response(
            "SUPPLIER_UNAVAILABLE",
            "Supplier API configuration is missing.",
        )

    counters = {
        "requests_made": 0,
        "pages_fetched": 0,
    }

    rejected = []
    products_by_sku = {}
    cursor = None

    session = requests.Session()

    try:
        headers = {"X-Api-Key": api_key}

        # Fetch and validate every page before touching the database.
        while True:
            params = {"limit": PAGE_SIZE}
            if cursor:
                params["cursor"] = cursor

            response = _supplier_get(
                session,
                f"{base_url}/v1/products",
                headers,
                params,
                counters,
            )

            try:
                payload = response.json()
            except ValueError as exc:
                raise RuntimeError(
                    "Supplier returned invalid JSON"
                ) from exc

            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("items"), list)
            ):
                raise RuntimeError(
                    "Supplier response must contain an items list"
                )

            counters["pages_fetched"] += 1

            for raw_item in payload["items"]:
                item = _parse_supplier_item(raw_item, rejected)
                if item is None:
                    continue

                sku = item["sku"]
                previous = products_by_sku.get(sku)

                # When a SKU appears on multiple pages, retain the
                # record with the latest updated_at timestamp.
                if previous is None or str(
                    item.get("updated_at", "")
                ) >= str(previous.get("updated_at", "")):
                    products_by_sku[sku] = item

            next_cursor = payload.get("next_cursor")

            if next_cursor is None or next_cursor == "":
                break

            if not isinstance(next_cursor, str):
                raise RuntimeError("Supplier returned an invalid cursor")

            if next_cursor == cursor:
                raise RuntimeError("Supplier pagination cursor did not advance")

            cursor = next_cursor

    except Exception as exc:
        return _supplier_error(exc)

    finally:
        session.close()

    created = 0
    updated = 0
    unchanged = 0

    try:
        with transaction.atomic():
            # Stable ordering reduces the chance of inconsistent lock
            # ordering when concurrent syncs run.
            for sku in sorted(products_by_sku):
                item = products_by_sku[sku]
                price = item["_parsed_price"]

                defaults = {
                    "name": str(item.get("name") or sku),
                    "category": str(item.get("category") or ""),
                    "brand": str(item.get("brand") or ""),
                    "vehicle_fitment": str(
                        item.get("vehicle_fitment") or ""
                    ),
                    "description": str(item.get("description") or ""),
                    "unit_price": price,
                }

                product = (
                    Product.objects.select_for_update()
                    .filter(sku=sku)
                    .first()
                )

                if product is None:
                    product = Product.objects.create(
                        sku=sku,
                        **defaults,
                    )

                    # Supplier data must never set or overwrite stock.
                    Inventory.objects.get_or_create(
                        product=product,
                        defaults={"quantity": 0},
                    )

                    created += 1
                    continue

                changed = any(
                    getattr(product, field) != value
                    for field, value in defaults.items()
                )

                if changed:
                    for field, value in defaults.items():
                        setattr(product, field, value)

                    product.save()
                    updated += 1
                else:
                    unchanged += 1

    except Exception as exc:
        # The transaction rolls back all product changes if any
        # database operation fails.
        return _error_response(
            "SUPPLIER_UNAVAILABLE",
            f"Supplier sync could not be applied: {exc}",
        )

    return JsonResponse({
        "created": created,
        "updated": updated,
        "unchanged": unchanged,
        "rejected": rejected,
        "pages_fetched": counters["pages_fetched"],
        "requests_made": counters["requests_made"],
    })
