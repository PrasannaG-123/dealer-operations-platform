# DealerFlow — Smart Dealer Management Platform

A Django-powered dealer management platform designed to simplify automotive spare-parts operations through inventory tracking, order management, demand forecasting, reorder recommendations, and an AI-powered dealer assistant.

DealerFlow brings essential dealer operations into one dashboard, helping users monitor stock, manage orders, identify products that may need replenishment, and access operational assistance from a single interface.

## Overview

Managing spare-parts inventory involves keeping stock information accurate, processing dealer orders, identifying products that may run low, and responding quickly to operational questions.

DealerFlow provides a centralized web application for these workflows. Its dashboard offers an overview of the system, while dedicated modules handle products, inventory, orders, forecasting, and the dealer assistant.

## Key Features

### 1. Dashboard
- Provides a centralized overview of dealer operations.
- Displays product, dealer, and order counts.
- Shows inventory-related information and reorder suggestions where available.

### 2. Product Catalogue
- Browse the available automotive spare-parts catalogue.
- Search for products.
- View product details such as SKU, name, category, brand, price, and stock information.
- Navigate through paginated product results.

### 3. Inventory Management
- View product stock levels.
- Update inventory quantities.
- Record a reason for stock adjustments.
- Review updated quantities through the inventory interface.

### 4. Order Management
- Create dealer orders using product SKUs and quantities.
- Calculate order totals, including applicable tax.
- Track order status.
- Confirm or cancel orders through the available order actions.
- Validate order information before processing.

### 5. Demand Forecasting
- Request a forecast for a selected product SKU.
- Use forecast results to support inventory planning.
- Review reorder suggestions to identify products that may require replenishment.

Forecasts and reorder recommendations are intended to support operational decisions; they should be reviewed alongside actual stock and business requirements.

### 6. AI-Powered Dealer Assistant
- Provides a conversational interface for dealer-related assistance.
- Accepts user messages through the assistant interface.
- Connects to the application's assistant API for responses.

The assistant's available capabilities depend on the configured backend and any connected AI service.

### 7. Supplier Synchronization
- Includes a supplier synchronization API for retrieving supplier data.
- Supports synchronization reporting for created, updated, unchanged, and rejected records.

Actual synchronization results depend on supplier API availability and configuration.

## How It Works

DealerFlow follows a browser-to-backend architecture.

1. **User interface:** The web dashboard provides the pages and forms used to manage products, inventory, orders, forecasts, and assistant conversations.
2. **Frontend requests:** JavaScript sends HTTP requests to the Django API when users load data or submit actions.
3. **Backend processing:** Django handles requests, applies validation and business logic, and interacts with the database.
4. **Data persistence:** The configured database stores application records, such as products, dealers, inventory, and orders.
5. **API responses:** The backend returns JSON responses, which the frontend uses to update tables, forms, status messages, and dashboard information.
6. **Planning and assistance:** Forecasting, reorder suggestions, supplier synchronization, and the assistant are accessed through their respective backend endpoints.

### Example Workflow: Processing an Order

1. The user opens the Orders page.
2. The user supplies a dealer identifier and the requested product SKUs and quantities.
3. The frontend sends the order details to the Django API.
4. The backend validates the request and creates the order.
5. The application returns the order details and status.
6. The user can then use the available actions to confirm or cancel the order, subject to the backend's order-state rules.

## Technology Stack

- **Backend:** Python, Django
- **Frontend:** HTML, CSS, JavaScript
- **API communication:** HTTP and JSON
- **Database:** PostgreSQL, when configured through the application's database connection
- **Additional capabilities:** Forecasting, reorder recommendations, supplier synchronization, and an AI assistant

## Project Structure

```text
dealerflow/
├── core/
│   ├── templates/
│   │   └── core/
│   │       └── index.html
│   ├── static/
│   │   └── core/
│   │       ├── app.css
│   │       └── app.js
│   └── views.py
├── manage.py
├── requirements.txt
└── README.md
```

The exact project may contain additional Django configuration, application modules, migrations, and supporting files.

## Getting Started

### Prerequisites

- Python 3.10 or a compatible version required by the project's dependencies
- Git
- PostgreSQL, if required by the configured database settings

### 1. Clone the repository

```bash
git clone https://github.com/YOUR-USERNAME/dealerflow.git
cd dealerflow
```

Replace `YOUR-USERNAME` with your GitHub username.

### 2. Create and activate a virtual environment

**Windows PowerShell**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 3. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 4. Configure environment variables

Set the database connection and other required settings according to your project's Django configuration.

For example, if the application reads `DATABASE_URL`:

```powershell
$env:DATABASE_URL = Read-Host "Enter your PostgreSQL DATABASE_URL"
```

Supplier integration settings may also be required when testing synchronization. Configure credentials locally; never commit secrets or passwords to GitHub.

### 5. Apply database migrations

```powershell
python manage.py migrate
```

If the project provides a seed-data command, use the command documented by the project to load the required sample data.

### 6. Run the development server

```powershell
python manage.py runserver 127.0.0.1:8000
```

Open the application at:

http://127.0.0.1:8000/

### 7. Run basic checks

```powershell
python manage.py check
python -m py_compile core\views.py
```

If the project includes smoke-test scripts, run the appropriate script after starting the server and configuring the required database and integrations.

## API Overview

The application exposes endpoints for its main operational features. The following routes are used by the current frontend integration:

| Endpoint | Purpose |
|---|---|
| `/api/health/` | Check API health |
| `/api/products/` | List and search products |
| `/api/products/<sku>/` | Retrieve product details |
| `/api/inventory/<sku>/` | Update inventory |
| `/api/orders/` | Create and retrieve orders |
| `/api/orders/<order_number>/confirm/` | Confirm an order |
| `/api/orders/<order_number>/cancel/` | Cancel an order |
| `/api/forecast/<sku>/` | Request a product forecast |
| `/api/reorder-suggestions/` | Retrieve reorder suggestions |
| `/api/assistant/chat/` | Send a message to the dealer assistant |
| `/api/sync/supplier/` | Trigger supplier synchronization |

Availability and request formats depend on the corresponding backend implementations and configuration.

## Security Notes

- Keep `.env` files, database credentials, API keys, and Django secret keys out of version control.
- Use environment variables for sensitive configuration.
- Do not use the development server as a production deployment server.
- Apply suitable authentication, authorization, and deployment security settings before production use.

## Project Goals

DealerFlow demonstrates how a Django application can bring together dealer operations, inventory workflows, order processing, forecasting, and AI-assisted interactions in a single web interface.

The project is intended to make routine operations easier to access, improve visibility into inventory and orders, and provide a foundation for future enhancements.

## Future Enhancements

- Role-based access for administrators and dealers
- More detailed sales and inventory analytics
- Forecast accuracy evaluation and historical comparisons
- Improved audit logs and reporting
- Production deployment and automated testing
- Expanded assistant capabilities and integration monitoring

---

**Built with Python, Django, JavaScript, and PostgreSQL.**
