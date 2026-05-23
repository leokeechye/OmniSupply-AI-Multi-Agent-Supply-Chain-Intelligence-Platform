"""
Load INCOM 2024 supply-chain delay dataset into Railway Postgres.

Source: kaggle.com/datasets/pushpitkamboj/logistics-data-containing-real-world-data
Underlying data: DataCo Smart Supply Chain (15,549 rows) + INCOM delay label.

Populates THREE tables from one CSV:
  - orders               (direct mapping from INCOM columns)
  - shipments            (derived: shipping_date + label + shipping_mode)
  - financial_transactions (derived: one revenue tx per order)

INVENTORY is NOT touched — INCOM has no stock-level data, so synthetic
seed data stays in that table.

Usage:
    python scripts/load_incom.py --dry-run            # validate, no DB writes
    python scripts/load_incom.py                       # insert (keeps inventory)
    python scripts/load_incom.py --csv /path/to.csv    # custom CSV path

Requires DATABASE_URL in env or .env (postgresql://...).
"""
from __future__ import annotations

import argparse
import logging
import os
import random
import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import List, Tuple

import pandas as pd
from dotenv import load_dotenv

_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

from src.data.models import (  # noqa: E402
    FinancialTransaction,
    Order,
    Shipment,
)


SEED = 42
random.seed(SEED)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
log = logging.getLogger("incom_loader")


CARRIERS = ["DHL", "FedEx", "UPS", "Maersk", "Hapag-Lloyd"]
DELAY_REASONS = [
    "Customs hold",
    "Weather disruption at origin",
    "Port congestion",
    "Carrier capacity shortage",
    "Documentation issue",
    "Routing change after dispatch",
]

# shipping_mode → estimated lead time in days
LEAD_TIMES = {
    "Same Day": 1,
    "First Class": 2,
    "Second Class": 4,
    "Standard Class": 7,
}

# market → cost center
MARKET_TO_CC = {
    "Africa": "CC-AF-01",
    "Europe": "CC-EU-02",
    "LATAM": "CC-LA-03",
    "Pacific Asia": "CC-PA-04",
    "USCA": "CC-NA-05",
}

# customer_segment → business unit
SEGMENT_TO_BU = {
    "Consumer": "Retail",
    "Corporate": "Wholesale",
    "Home Office": "Enterprise",
}


def _id(row_id: float, prefix: str = "INC") -> str:
    """Stable unique string ID from a float (preserves precision)."""
    return f"{prefix}-{int(round(row_id * 1000)):011d}"


def _parse_dt(s: str) -> datetime:
    """Parse INCOM datetime '2015-08-12 00:00:00+01:00' → naive datetime UTC-ish."""
    dt = datetime.fromisoformat(s)
    # Strip tz for SQLAlchemy compatibility with the DateTime column
    return dt.replace(tzinfo=None)


def _ship_status(order_status: str, label: int) -> str:
    """Derive shipment status from order_status + delay label."""
    os_ = (order_status or "").upper()
    if os_ in ("COMPLETE", "CLOSED"):
        return "delivered"
    if os_ in ("CANCELED", "CANCELLED"):
        return "cancelled"
    # Anything pending/processing → in_transit, but flag as delayed if label==1
    if label == 1:
        return "delayed"
    return "in_transit"


def build_records(df: pd.DataFrame) -> Tuple[List[Order], List[Shipment], List[FinancialTransaction]]:
    """Convert each INCOM row into (Order, Shipment, FinancialTransaction)."""
    orders: List[Order] = []
    shipments: List[Shipment] = []
    transactions: List[FinancialTransaction] = []

    seen_order_ids: set[str] = set()

    for _, r in df.iterrows():
        order_id = _id(r["order_id"], "INC-ORD")
        if order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)

        product_id = str(int(r["product_card_id"]))
        order_dt = _parse_dt(r["order_date"])
        ship_dt = _parse_dt(r["shipping_date"])
        ship_mode = r["shipping_mode"]
        label = int(r["label"])
        order_status = str(r["order_status"])
        qty = max(int(r["order_item_quantity"]), 1)

        list_price = float(r["order_item_product_price"])
        discount_pct = float(r["order_item_discount_rate"])
        discount = float(r["order_item_discount"])
        total_amount = float(r["order_item_total_amount"])
        profit = float(r["order_profit_per_order"])
        sale_price_per_unit = total_amount / qty if qty else total_amount
        cost_per_unit = sale_price_per_unit - (profit / qty if qty else profit)

        orders.append(
            Order(
                order_id=order_id,
                order_date=order_dt,
                ship_mode=ship_mode,
                segment=str(r["customer_segment"]),
                country=str(r["order_country"])[:100],
                city=str(r["order_city"])[:100],
                state=str(r["order_state"])[:100],
                postal_code=None,
                region=str(r["order_region"])[:50],
                category=str(r["category_name"])[:100],
                sub_category=str(r["department_name"])[:100],
                product_id=product_id,
                cost_price=Decimal(f"{max(cost_per_unit, 0):.2f}"),
                list_price=Decimal(f"{list_price:.2f}"),
                quantity=qty,
                discount_percent=Decimal(f"{discount_pct:.2f}"),
                discount=Decimal(f"{discount:.2f}"),
                sale_price=Decimal(f"{sale_price_per_unit:.2f}"),
                profit=Decimal(f"{profit:.2f}"),
                is_returned=order_status in ("CANCELED", "SUSPECTED_FRAUD"),
            )
        )

        # Derived shipment
        lead = LEAD_TIMES.get(ship_mode, 7)
        expected = ship_dt + timedelta(days=lead)
        if label == -1:
            actual = expected - timedelta(days=random.randint(1, 3))
        elif label == 0:
            actual = expected
        else:  # label == 1, delayed
            actual = expected + timedelta(days=random.randint(3, 14))

        status = _ship_status(order_status, label)
        if status in ("in_transit", "cancelled"):
            actual_for_db = None
        else:
            actual_for_db = actual

        shipments.append(
            Shipment(
                shipment_id=_id(r["order_id"], "INC-SHP"),
                product_id=product_id,
                origin_port=None,
                destination_port=str(r["order_city"])[:100],
                carrier=CARRIERS[int(r["order_id"]) % len(CARRIERS)],
                shipment_date=ship_dt,
                expected_delivery=expected,
                actual_delivery=actual_for_db,
                quantity=qty,
                weight_kg=None,
                freight_cost=None,
                insurance_cost=None,
                customs_cost=None,
                status=status,
                delay_reason=random.choice(DELAY_REASONS) if label == 1 else None,
            )
        )

        # Derived financial transaction (revenue)
        transactions.append(
            FinancialTransaction(
                transaction_id=_id(r["order_id"], "INC-TX"),
                transaction_date=order_dt,
                transaction_type="revenue",
                category="product_sales",
                subcategory=str(r["category_name"])[:100],
                amount=Decimal(f"{total_amount:.2f}"),
                currency="USD",
                cost_center=MARKET_TO_CC.get(str(r["market"]), "CC-OTH-99"),
                business_unit=SEGMENT_TO_BU.get(str(r["customer_segment"]), "Other"),
                payment_method=str(r["payment_type"]).lower(),
                vendor_id=None,
                notes=None,
            )
        )

    return orders, shipments, transactions


def _clear_non_inventory(db) -> None:
    """Clear orders, shipments, financial_transactions — leave inventory alone."""
    from src.storage.sql.models import (
        FinancialTransactionDB,
        OrderDB,
        ShipmentDB,
    )

    log.info("Clearing orders, shipments, financial_transactions (inventory preserved)…")
    with db.get_session() as session:
        n_tx = session.query(FinancialTransactionDB).delete()
        n_sh = session.query(ShipmentDB).delete()
        n_or = session.query(OrderDB).delete()
        log.info(f"  cleared: {n_or} orders, {n_sh} shipments, {n_tx} transactions")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--csv", default=str(_REPO_ROOT / "data" / "incom2024_delay_example_dataset.csv"))
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--limit", type=int, default=None, help="Cap rows loaded (for quick tests)")
    args = p.parse_args()

    load_dotenv(_REPO_ROOT / ".env")

    csv_path = Path(args.csv)
    if not csv_path.is_file():
        log.error(f"CSV not found: {csv_path}")
        return 1

    log.info(f"Reading {csv_path}…")
    df = pd.read_csv(csv_path)
    if args.limit:
        df = df.head(args.limit)
    log.info(f"  {len(df):,} rows × {df.shape[1]} columns")

    log.info("Building records (this loops 15K rows, ~5–10s)…")
    orders, shipments, transactions = build_records(df)
    log.info(f"  -> {len(orders):,} orders, {len(shipments):,} shipments, {len(transactions):,} transactions")
    log.info(f"  sample order: {orders[0].model_dump(mode='json')}")
    log.info(f"  sample shipment status mix: " + ", ".join(
        f"{s}={sum(1 for x in shipments if x.status == s)}"
        for s in ("delivered", "delayed", "in_transit", "cancelled")
    ))

    if args.dry_run:
        log.info("--dry-run: skipping DB writes.")
        return 0

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        log.error("DATABASE_URL is not set in env or .env.")
        return 1

    from src.storage.sql.database import DatabaseClient

    log.info(f"Connecting to: {database_url.split('@')[-1] if '@' in database_url else database_url}")
    db = DatabaseClient(database_url=database_url)

    _clear_non_inventory(db)

    log.info("Inserting orders…")
    db.upsert_orders(orders)  # already batches internally

    # insert_shipments / insert_transactions push all rows in one transaction —
    # too slow over Railway's public proxy. Batch them here.
    BATCH = 1000
    log.info(f"Inserting shipments in batches of {BATCH}…")
    for i in range(0, len(shipments), BATCH):
        chunk = shipments[i : i + BATCH]
        db.insert_shipments(chunk)
        log.info(f"  shipments {i + len(chunk):,}/{len(shipments):,}")

    log.info(f"Inserting transactions in batches of {BATCH}…")
    for i in range(0, len(transactions), BATCH):
        chunk = transactions[i : i + BATCH]
        db.insert_transactions(chunk)
        log.info(f"  transactions {i + len(chunk):,}/{len(transactions):,}")

    counts = db.get_table_counts()
    log.info("DB now contains:")
    for table, count in counts.items():
        log.info(f"  - {table}: {count:,}")

    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
