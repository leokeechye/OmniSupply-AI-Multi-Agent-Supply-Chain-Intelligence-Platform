"""
Synthetic seed data for OmniSupply.

Generates ~200 each of Order / Shipment / InventoryItem / FinancialTransaction
using Faker, then inserts via the existing DatabaseClient. The shapes match
src/data/models.py and the DB columns in src/storage/sql/models.py.

Use this to populate an empty Postgres so the agents have something to analyse.
Designed for one-shot ingestion against Railway Postgres — point it at the
public connection URL, run once, done.

Usage:
    # Dry run — generate + count, no DB writes (works offline)
    python scripts/seed.py --dry-run

    # Real run — needs DATABASE_URL pointing at a postgres:// instance
    export DATABASE_URL="postgresql://postgres:<pwd>@<host>.proxy.rlwy.net:<port>/railway"
    python scripts/seed.py

    # Reset (clear existing rows before inserting)
    python scripts/seed.py --reset
"""
from __future__ import annotations

import argparse
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from faker import Faker

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data.models import (
    FinancialTransaction,
    InventoryItem,
    Order,
    Shipment,
)


SEED = 42
random.seed(SEED)
fake = Faker()
Faker.seed(SEED)


SHIP_MODES = ["Standard Class", "Second Class", "First Class", "Same Day"]
SEGMENTS = ["Consumer", "Corporate", "Home Office"]
REGIONS = ["West", "East", "South", "Central"]
CATEGORIES = {
    "Furniture": ["Chairs", "Tables", "Bookcases", "Furnishings"],
    "Office Supplies": ["Paper", "Binders", "Storage", "Art", "Fasteners"],
    "Technology": ["Phones", "Accessories", "Machines", "Copiers"],
}
CARRIERS = ["DHL", "FedEx", "UPS", "Maersk", "Hapag-Lloyd"]
PORTS = ["Shanghai", "Singapore", "Rotterdam", "Los Angeles", "Hamburg", "Dubai", "Antwerp"]
SHIPMENT_STATUSES = ["delivered", "in_transit", "delayed", "cancelled"]
DELAY_REASONS = [
    "Customs hold",
    "Weather disruption at origin",
    "Port congestion",
    "Carrier capacity shortage",
    "Documentation issue",
]
WAREHOUSES = ["WH-SF-01", "WH-NJ-02", "WH-DAL-03", "WH-CHI-04", "WH-ATL-05"]
TX_TYPES = ["revenue", "expense", "refund", "adjustment"]
TX_CATEGORIES = {
    "revenue": ["product_sales", "subscription", "service_fee"],
    "expense": ["freight", "warehousing", "marketing", "salaries", "software"],
    "refund": ["return", "chargeback"],
    "adjustment": ["inventory_writedown", "currency_revaluation"],
}
PAYMENT_METHODS = ["wire", "ach", "credit_card", "po"]
COST_CENTERS = ["CC-OPS-01", "CC-SALES-02", "CC-MKT-03", "CC-IT-04", "CC-FIN-05"]
BUSINESS_UNITS = ["Retail", "Wholesale", "Enterprise"]


def _gen_orders(n: int) -> List[Order]:
    orders = []
    for _ in range(n):
        category = random.choice(list(CATEGORIES.keys()))
        sub_category = random.choice(CATEGORIES[category])
        cost = round(random.uniform(5, 800), 2)
        list_price = round(cost * random.uniform(1.2, 2.5), 2)
        quantity = random.randint(1, 10)
        discount_pct = round(random.choice([0, 0, 0, 0.05, 0.1, 0.15, 0.2]), 2)
        discount = round(list_price * discount_pct, 2)
        sale_price = round(list_price - discount, 2)
        profit = round((sale_price - cost) * quantity, 2)
        orders.append(
            Order(
                order_id=fake.unique.bothify(text="ORD-####-????").upper(),
                order_date=fake.date_time_between(start_date="-180d", end_date="now"),
                ship_mode=random.choice(SHIP_MODES),
                segment=random.choice(SEGMENTS),
                country=fake.country()[:100],
                city=fake.city()[:100],
                state=fake.state()[:100],
                postal_code=fake.postcode()[:20],
                region=random.choice(REGIONS),
                category=category,
                sub_category=sub_category,
                product_id=f"PROD-{random.randint(1000, 9999)}",
                cost_price=Decimal(str(cost)),
                list_price=Decimal(str(list_price)),
                quantity=quantity,
                discount_percent=Decimal(str(discount_pct)),
                discount=Decimal(str(discount)),
                sale_price=Decimal(str(sale_price)),
                profit=Decimal(str(profit)),
                is_returned=random.random() < 0.08,
            )
        )
    return orders


def _gen_shipments(n: int) -> List[Shipment]:
    shipments = []
    for _ in range(n):
        shipment_date = fake.date_time_between(start_date="-180d", end_date="-7d")
        expected_lead = random.randint(7, 35)
        expected_delivery = shipment_date + timedelta(days=expected_lead)
        status = random.choices(
            SHIPMENT_STATUSES, weights=[0.6, 0.2, 0.15, 0.05], k=1
        )[0]
        actual_delivery = None
        delay_reason = None
        if status == "delivered":
            actual_delivery = expected_delivery + timedelta(days=random.randint(-3, 6))
        elif status == "delayed":
            actual_delivery = expected_delivery + timedelta(days=random.randint(4, 21))
            delay_reason = random.choice(DELAY_REASONS)
        # in_transit and cancelled leave actual_delivery null

        freight = round(random.uniform(150, 3500), 2)
        shipments.append(
            Shipment(
                shipment_id=fake.unique.bothify(text="SHP-#####-???").upper(),
                product_id=f"PROD-{random.randint(1000, 9999)}",
                origin_port=random.choice(PORTS),
                destination_port=random.choice(PORTS),
                carrier=random.choice(CARRIERS),
                shipment_date=shipment_date,
                expected_delivery=expected_delivery,
                actual_delivery=actual_delivery,
                quantity=random.randint(50, 5000),
                weight_kg=Decimal(str(round(random.uniform(20, 25000), 2))),
                freight_cost=Decimal(str(freight)),
                insurance_cost=Decimal(str(round(freight * random.uniform(0.01, 0.05), 2))),
                customs_cost=Decimal(str(round(freight * random.uniform(0.05, 0.18), 2))),
                status=status,
                delay_reason=delay_reason,
            )
        )
    return shipments


def _gen_inventory(n: int) -> List[InventoryItem]:
    items = []
    for _ in range(n):
        category = random.choice(list(CATEGORIES.keys()))
        items.append(
            InventoryItem(
                sku=fake.unique.bothify(text="SKU-#####-???").upper(),
                product_id=f"PROD-{random.randint(1000, 9999)}",
                product_name=fake.catch_phrase()[:255],
                category=category,
                warehouse_location=random.choice(WAREHOUSES),
                stock_quantity=random.randint(0, 2000),
                reorder_level=random.randint(50, 500),
                reorder_quantity=random.randint(100, 1000),
                unit_cost=Decimal(str(round(random.uniform(2, 500), 2))),
                last_restock_date=fake.date_time_between(start_date="-90d", end_date="now"),
                lead_time_days=random.randint(3, 45),
                supplier_id=f"SUP-{random.randint(100, 999)}",
            )
        )
    return items


def _gen_transactions(n: int) -> List[FinancialTransaction]:
    txs = []
    for _ in range(n):
        tx_type = random.choices(TX_TYPES, weights=[0.45, 0.4, 0.1, 0.05], k=1)[0]
        category = random.choice(TX_CATEGORIES[tx_type])
        # Revenues are positive, expenses/refunds/adjustments are negative
        magnitude = round(random.uniform(200, 50000), 2)
        amount = magnitude if tx_type == "revenue" else -magnitude
        txs.append(
            FinancialTransaction(
                transaction_id=fake.unique.bothify(text="TX-######").upper(),
                transaction_date=fake.date_time_between(start_date="-180d", end_date="now"),
                transaction_type=tx_type,
                category=category,
                subcategory=fake.word(),
                amount=Decimal(str(amount)),
                currency="USD",
                cost_center=random.choice(COST_CENTERS),
                business_unit=random.choice(BUSINESS_UNITS),
                payment_method=random.choice(PAYMENT_METHODS),
                vendor_id=f"VND-{random.randint(100, 999)}" if tx_type != "revenue" else None,
                notes=None,
            )
        )
    return txs


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--orders", type=int, default=200)
    parser.add_argument("--shipments", type=int, default=200)
    parser.add_argument("--inventory", type=int, default=200)
    parser.add_argument("--transactions", type=int, default=200)
    parser.add_argument("--reset", action="store_true", help="Clear all rows before inserting.")
    parser.add_argument("--dry-run", action="store_true", help="Generate + count, no DB writes.")
    args = parser.parse_args()

    load_dotenv()

    print(f"Generating: {args.orders} orders, {args.shipments} shipments, "
          f"{args.inventory} inventory items, {args.transactions} transactions…")
    orders = _gen_orders(args.orders)
    shipments = _gen_shipments(args.shipments)
    inventory = _gen_inventory(args.inventory)
    transactions = _gen_transactions(args.transactions)

    sample_order = orders[0].model_dump(mode="json")
    print(f"\nSample order:\n  {sample_order}")

    if args.dry_run:
        print(f"\n--dry-run: generated {len(orders) + len(shipments) + len(inventory) + len(transactions)} "
              "records total. No DB writes.")
        return 0

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        print("\nERROR: DATABASE_URL is not set. Export it or add to .env, then re-run.")
        print("On Railway: copy the public Postgres URL from your Postgres service's "
              "Connect tab → 'Postgres Connection URL'.")
        return 1

    from src.storage.sql.database import DatabaseClient

    print(f"\nConnecting to: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    db = DatabaseClient(database_url=database_url)

    if args.reset:
        print("Clearing existing data (--reset)…")
        db.clear_all_data()

    print("Inserting orders…")
    db.upsert_orders(orders)
    print("Inserting shipments…")
    db.insert_shipments(shipments)
    print("Inserting inventory…")
    db.insert_inventory(inventory)
    print("Inserting transactions…")
    db.insert_transactions(transactions)

    counts = db.get_table_counts()
    print(f"\nDB now contains:")
    for table, count in counts.items():
        print(f"  - {table}: {count:,}")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
