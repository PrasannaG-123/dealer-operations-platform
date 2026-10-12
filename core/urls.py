from django.urls import path
from . import views
from .supplier_sync import sync_supplier

urlpatterns = [
    path("health/", views.health, name="health"),
    path("products/", views.products, name="products"),
    path("products/<str:sku>/", views.product_detail, name="product-detail"),
    path("inventory/<str:sku>/", views.inventory_update, name="inventory-update"),
    path("dealers/", views.dealers, name="dealers"),
    path("dealers/<str:dealer_code>/", views.dealer_detail, name="dealer-detail"),
    path("orders/", views.orders, name="orders"),
    path("orders/<str:order_number>/", views.order_detail, name="order-detail"),
    path(
        "orders/<str:order_number>/<str:action>/",
        views.order_action,
        name="order-action",
    ),
    path("assistant/chat/", views.assistant_chat, name="assistant-chat"),
    path("forecast/<str:sku>/", views.sku_forecast, name="forecast"),
    path("reorder-suggestions/", views.reorder_suggestions, name="reorder-suggestions"),
    path("sync/supplier/", sync_supplier, name="sync-supplier"),
]
