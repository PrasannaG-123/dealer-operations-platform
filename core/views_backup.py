
import json
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import Dealer, Inventory, Product, Order, OrderItem


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def parse_json_body(request):
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, JsonResponse(
            {"error": "Invalid JSON body"},
            status=400,
        )

    if not isinstance(payload, dict):
        return None, JsonResponse(
            {"error": "JSON body must be an object"},
            status=400,
        )

    return payload, None


def decimal_value(value, field_name):
    try:
        number = Decimal(str(value))

        if not number.is_finite() or number < 0:
            raise InvalidOperation

        return number, None

    except (InvalidOperation, ValueError, TypeError):
        return None, JsonResponse(
            {
                "error": (
                    f"{field_name} must be a valid "
                    "non-negative number"
                )
            },
            status=400,
        )


def product_data(product):
    return {
        "sku": product.sku,
        "name": product.name,
        "category": product.category,
        "brand": product.brand,
        "vehicle_fitment": product.vehicle_fitment,
        "description": product.description,
        "unit_price": str(product.unit_price),
        "gst_rate": str(product.gst_rate),
        "is_active": product.is_active,
    }


def dealer_data(dealer):
    return {
        "dealer_code": dealer.dealer_code,
        "name": dealer.name,
        "city": dealer.city,
        "phone": dealer.phone,
        "email": dealer.email,
        "gstin": dealer.gstin,
        "credit_limit": str(dealer.credit_limit),
    }


def order_data(order):
    return {
        "order_number": order.order_number,
        "dealer_code": order.dealer.dealer_code,
        "status": order.status,
        "subtotal": str(order.subtotal),
        "gst_amount": str(order.gst_amount),
        "total_amount": str(order.total_amount),
        "created_at": order.created_at.isoformat(),
        "items": [
            {
                "sku": item.product.sku,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "gst_rate": str(item.gst_rate),
                "gst_amount": str(item.gst_amount),
                "line_total": str(item.line_total),
            }
            for item in order.items.select_related("product").all()
        ],
    }


# --------------------------------------------------
# Health
# --------------------------------------------------

@require_http_methods(["GET"])
def health(request):
    return JsonResponse({"status": "ok"})


# --------------------------------------------------
# Products
# --------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "POST"])
def products(request):
    if request.method == "GET":
        queryset = Product.objects.all().order_by("name")
        data = [product_data(product) for product in queryset]

        return JsonResponse({
            "count": len(data),
            "results": data,
        })

    payload, error = parse_json_body(request)
    if error:
        return error

    required = ("sku", "name", "unit_price")
    missing = [
        field
        for field in required
        if field not in payload or payload[field] in ("", None)
    ]

    if missing:
        return JsonResponse(
            {
                "error": "Missing required fields",
                "fields": missing,
            },
            status=400,
        )

    if (
        not isinstance(payload["sku"], str)
        or not payload["sku"].strip()
    ):
        return JsonResponse(
            {"error": "sku must be a non-empty string"},
            status=400,
        )

    if (
        not isinstance(payload["name"], str)
        or not payload["name"].strip()
    ):
        return JsonResponse(
            {"error": "name must be a non-empty string"},
            status=400,
        )

    if (
        "is_active" in payload
        and not isinstance(payload["is_active"], bool)
    ):
        return JsonResponse(
            {"error": "is_active must be true or false"},
            status=400,
        )

    unit_price, error = decimal_value(
        payload["unit_price"],
        "unit_price",
    )
    if error:
        return error

    gst_rate, error = decimal_value(
        payload.get("gst_rate", "18.00"),
        "gst_rate",
    )
    if error:
        return error

    sku = payload["sku"].strip()

    if Product.objects.filter(sku=sku).exists():
        return JsonResponse(
            {"error": "A product with this SKU already exists"},
            status=409,
        )

    product = Product.objects.create(
        sku=sku,
        name=payload["name"].strip(),
        category=payload.get("category", ""),
        brand=payload.get("brand", ""),
        vehicle_fitment=payload.get("vehicle_fitment", ""),
        description=payload.get("description", ""),
        unit_price=unit_price,
        gst_rate=gst_rate,
        is_active=payload.get("is_active", True),
    )

    return JsonResponse(product_data(product), status=201)


@csrf_exempt
@require_http_methods(["GET", "PATCH"])
def product_detail(request, sku):
    product = get_object_or_404(Product, sku=sku)

    if request.method == "GET":
        return JsonResponse(product_data(product))

    payload, error = parse_json_body(request)
    if error:
        return error

    allowed_fields = {
        "name",
        "category",
        "brand",
        "vehicle_fitment",
        "description",
        "unit_price",
        "gst_rate",
        "is_active",
    }

    unknown_fields = set(payload) - allowed_fields
    if unknown_fields:
        return JsonResponse(
            {
                "error": "Unknown fields",
                "fields": sorted(unknown_fields),
            },
            status=400,
        )

    for field in (
        "name",
        "category",
        "brand",
        "vehicle_fitment",
        "description",
    ):
        if field in payload:
            if not isinstance(payload[field], str):
                return JsonResponse(
                    {"error": f"{field} must be a string"},
                    status=400,
                )

            setattr(product, field, payload[field])

    for field in ("unit_price", "gst_rate"):
        if field in payload:
            value, error = decimal_value(payload[field], field)
            if error:
                return error

            setattr(product, field, value)

    if "is_active" in payload:
        if not isinstance(payload["is_active"], bool):
            return JsonResponse(
                {"error": "is_active must be true or false"},
                status=400,
            )

        product.is_active = payload["is_active"]

    product.save()
    return JsonResponse(product_data(product))


# --------------------------------------------------
# Inventory
# GET checks stock; PUT updates stock
# --------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "PUT"])
def inventory_update(request, sku):
    product = get_object_or_404(Product, sku=sku)

    # GET /api/inventory/<sku>/
    if request.method == "GET":
        inventory = Inventory.objects.filter(
            product=product
        ).first()

        if inventory is None:
            return JsonResponse(
                {"error": f"Inventory not found for product: {sku}"},
                status=404,
            )

        return JsonResponse({
            "sku": product.sku,
            "name": product.name,
            "quantity": inventory.quantity,
        })

    # PUT /api/inventory/<sku>/
    payload, error = parse_json_body(request)
    if error:
        return error

    if "quantity" not in payload:
        return JsonResponse(
            {"error": "A quantity field is required"},
            status=400,
        )

    quantity = payload["quantity"]

    if (
        isinstance(quantity, bool)
        or not isinstance(quantity, int)
        or quantity < 0
    ):
        return JsonResponse(
            {"error": "quantity must be a non-negative integer"},
            status=400,
        )

    inventory, _ = Inventory.objects.update_or_create(
        product=product,
        defaults={"quantity": quantity},
    )

    return JsonResponse({
        "sku": product.sku,
        "name": product.name,
        "quantity": inventory.quantity,
    })


# --------------------------------------------------
# Dealers
# --------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "POST"])
def dealers(request):
    if request.method == "GET":
        queryset = Dealer.objects.all().order_by("name")
        data = [dealer_data(dealer) for dealer in queryset]

        return JsonResponse({
            "count": len(data),
            "results": data,
        })

    payload, error = parse_json_body(request)
    if error:
        return error

    required = ("dealer_code", "name", "city", "credit_limit")
    missing = [
        field
        for field in required
        if field not in payload or payload[field] in ("", None)
    ]

    if missing:
        return JsonResponse(
            {
                "error": "Missing required fields",
                "fields": missing,
            },
            status=400,
        )

    credit_limit, error = decimal_value(
        payload["credit_limit"],
        "credit_limit",
    )
    if error:
        return error

    dealer_code = payload["dealer_code"]

    if (
        not isinstance(dealer_code, str)
        or not dealer_code.strip()
    ):
        return JsonResponse(
            {"error": "dealer_code must be a non-empty string"},
            status=400,
        )

    dealer_code = dealer_code.strip()

    if Dealer.objects.filter(dealer_code=dealer_code).exists():
        return JsonResponse(
            {"error": "Dealer already exists"},
            status=409,
        )

    dealer = Dealer.objects.create(
        dealer_code=dealer_code,
        name=payload["name"],
        city=payload["city"],
        phone=payload.get("phone", ""),
        email=payload.get("email", ""),
        gstin=payload.get("gstin", ""),
        credit_limit=credit_limit,
    )

    return JsonResponse(dealer_data(dealer), status=201)


@require_http_methods(["GET"])
def dealer_detail(request, dealer_code):
    dealer = get_object_or_404(
        Dealer,
        dealer_code=dealer_code,
    )
    return JsonResponse(dealer_data(dealer))


# --------------------------------------------------
# Orders: list and create
# --------------------------------------------------

@csrf_exempt
@require_http_methods(["GET", "POST"])
def orders(request):
    # GET /api/orders/
    if request.method == "GET":
        queryset = (
            Order.objects.select_related("dealer")
            .prefetch_related("items__product")
            .order_by("-created_at")
        )

        results = [order_data(order) for order in queryset]

        return JsonResponse({
            "count": len(results),
            "results": results,
        })

    # POST /api/orders/
    payload, error = parse_json_body(request)
    if error:
        return error

    dealer_code = payload.get("dealer_code")
    items = payload.get("items")

    if not dealer_code:
        return JsonResponse(
            {"error": "dealer_code is required"},
            status=400,
        )

    if not isinstance(items, list) or not items:
        return JsonResponse(
            {"error": "items must be a non-empty list"},
            status=400,
        )

    # Validate all items before changing stock.
    seen_skus = set()
    validated_items = []

    for item in items:
        if not isinstance(item, dict):
            return JsonResponse(
                {"error": "Each item must be an object"},
                status=400,
            )

        sku = item.get("sku")
        quantity = item.get("quantity")

        if not isinstance(sku, str) or not sku.strip():
            return JsonResponse(
                {"error": "Each item needs a valid SKU"},
                status=400,
            )

        sku = sku.strip()

        if sku in seen_skus:
            return JsonResponse(
                {
                    "error": f"Duplicate SKU in order: {sku}",
                    "detail": (
                        "Include each product once with "
                        "its total quantity."
                    ),
                },
                status=400,
            )

        seen_skus.add(sku)

        if (
            isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity <= 0
        ):
            return JsonResponse(
                {
                    "error": (
                        f"Quantity for {sku} must be "
                        "a positive integer"
                    )
                },
                status=400,
            )

        validated_items.append({
            "sku": sku,
            "quantity": quantity,
        })

    try:
        with transaction.atomic():
            dealer = Dealer.objects.select_for_update().get(
                dealer_code=dealer_code
            )

            prepared_items = []
            subtotal = Decimal("0.00")
            total_gst = Decimal("0.00")

            skus = sorted(
                entry["sku"] for entry in validated_items
            )

            locked_products = {
                product.sku: product
                for product in Product.objects.filter(
                    sku__in=skus,
                    is_active=True,
                )
            }

            if len(locked_products) != len(skus):
                missing_skus = sorted(
                    set(skus) - set(locked_products)
                )

                return JsonResponse(
                    {
                        "error": (
                            "One or more products were "
                            "not found or are inactive"
                        ),
                        "skus": missing_skus,
                    },
                    status=400,
                )

            inventories = {
                inventory.product_id: inventory
                for inventory in (
                    Inventory.objects.select_for_update()
                    .filter(product_id__in=skus)
                    .order_by("product_id")
                )
            }

            for entry in validated_items:
                sku = entry["sku"]
                quantity = entry["quantity"]
                product = locked_products[sku]
                inventory = inventories.get(sku)

                if inventory is None:
                    return JsonResponse(
                        {
                            "error": (
                                f"Inventory not found for "
                                f"product: {sku}"
                            )
                        },
                        status=400,
                    )

                if inventory.quantity < quantity:
                    return JsonResponse(
                        {
                            "error": f"Insufficient stock for {sku}",
                            "available": inventory.quantity,
                            "requested": quantity,
                        },
                        status=400,
                    )

                line_subtotal = (
                    product.unit_price * quantity
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                line_gst = (
                    line_subtotal
                    * product.gst_rate
                    / Decimal("100")
                ).quantize(
                    Decimal("0.01"),
                    rounding=ROUND_HALF_UP,
                )

                line_total = line_subtotal + line_gst

                prepared_items.append({
                    "product": product,
                    "inventory": inventory,
                    "quantity": quantity,
                    "unit_price": product.unit_price,
                    "gst_rate": product.gst_rate,
                    "gst_amount": line_gst,
                    "line_total": line_total,
                })

                subtotal += line_subtotal
                total_gst += line_gst

            subtotal = subtotal.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            total_gst = total_gst.quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP,
            )
            total_amount = subtotal + total_gst

            # Generate a daily order number.
            now = timezone.localtime()
            date_part = now.strftime("%Y%m%d")
            prefix = f"ORD-{date_part}-"

            last_order = (
                Order.objects.filter(
                    order_number__startswith=prefix
                )
                .order_by("-order_number")
                .first()
            )

            sequence = (
                int(last_order.order_number[-4:]) + 1
                if last_order
                else 1
            )

            if sequence > 9999:
                return JsonResponse(
                    {"error": "Daily order number limit reached"},
                    status=409,
                )

            order_number = f"{prefix}{sequence:04d}"

            order = Order.objects.create(
                order_number=order_number,
                dealer=dealer,
                status=Order.Status.DRAFT,
                subtotal=subtotal,
                gst_amount=total_gst,
                total_amount=total_amount,
            )

            for prepared in prepared_items:
                OrderItem.objects.create(
                    order=order,
                    product=prepared["product"],
                    quantity=prepared["quantity"],
                    unit_price=prepared["unit_price"],
                    gst_rate=prepared["gst_rate"],
                    gst_amount=prepared["gst_amount"],
                    line_total=prepared["line_total"],
                )

                inventory = prepared["inventory"]
                inventory.quantity -= prepared["quantity"]
                inventory.save(
                    update_fields=["quantity", "updated_at"]
                )

    except Dealer.DoesNotExist:
        return JsonResponse(
            {"error": "Dealer not found"},
            status=404,
        )

    return JsonResponse(order_data(order), status=201)


# --------------------------------------------------
# Order lifecycle actions
# --------------------------------------------------

@csrf_exempt
@require_http_methods(["POST"])
def order_action(request, order_number, action):
    allowed_actions = {
        "confirm",
        "dispatch",
        "deliver",
        "cancel",
    }

    if action not in allowed_actions:
        return JsonResponse(
            {"error": "Unknown order action"},
            status=400,
        )

    with transaction.atomic():
        try:
            order = Order.objects.select_for_update().get(
                order_number=order_number
            )
        except Order.DoesNotExist:
            return JsonResponse(
                {"error": "Order not found"},
                status=404,
            )

        if action == "confirm":
            if order.status != Order.Status.DRAFT:
                return JsonResponse(
                    {
                        "error": (
                            "Only draft orders can be confirmed"
                        )
                    },
                    status=400,
                )

            order.status = Order.Status.CONFIRMED

        elif action == "dispatch":
            if order.status != Order.Status.CONFIRMED:
                return JsonResponse(
                    {
                        "error": (
                            "Only confirmed orders can be dispatched"
                        )
                    },
                    status=400,
                )

            order.status = Order.Status.DISPATCHED

        elif action == "deliver":
            if order.status != Order.Status.DISPATCHED:
                return JsonResponse(
                    {
                        "error": (
                            "Only dispatched orders can be delivered"
                        )
                    },
                    status=400,
                )

            order.status = Order.Status.DELIVERED

        elif action == "cancel":
            if order.status not in (
                Order.Status.DRAFT,
                Order.Status.CONFIRMED,
            ):
                return JsonResponse(
                    {
                        "error": (
                            "Only draft or confirmed orders "
                            "can be cancelled"
                        )
                    },
                    status=400,
                )

            # Restore stock inside the same transaction.
            items = list(
                order.items.select_related("product")
                .order_by("product_id")
            )

            for item in items:
                inventory = (
                    Inventory.objects.select_for_update()
                    .filter(product=item.product)
                    .first()
                )

                if inventory is None:
                    return JsonResponse(
                        {
                            "error": (
                                "Inventory not found for "
                                f"{item.product.sku}"
                            )
                        },
                        status=409,
                    )

                inventory.quantity += item.quantity
                inventory.save(
                    update_fields=["quantity", "updated_at"]
                )

            order.status = Order.Status.CANCELLED

        order.save(update_fields=["status", "updated_at"])

    return JsonResponse(order_data(order))
