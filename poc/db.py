"""Database initialisation for the PoC.

Creates (or opens) a SQLite database and loads receipt JSON files from
``data/receipts/`` into it, keyed to the fixed POC user_id.
Idempotent: receipts already in the DB (matched by merchant + datetime)
are skipped on subsequent runs.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker, Session

from models import Base, Receipt, ReceiptItem

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = PROJECT_ROOT / "data" / "receipts"
DB_PATH = Path(__file__).resolve().parent / "poc_receipts.db"


def build_engine(db_path: Path = DB_PATH):
    return create_engine(f"sqlite:///{db_path}", echo=False)


def init_db(user_id: uuid.UUID, db_path: Path = DB_PATH) -> sessionmaker[Session]:
    """Create schema and load receipt JSON files.  Returns a session factory."""
    engine = build_engine(db_path)
    Base.metadata.create_all(engine)
    factory = sessionmaker(engine, expire_on_commit=False)

    _ingest_receipts(factory, user_id)
    return factory


def _ingest_receipts(factory: sessionmaker[Session], user_id: uuid.UUID) -> int:
    """Load receipt JSON files not yet in the DB.  Returns the number inserted."""
    if not RECEIPTS_DIR.exists():
        return 0

    inserted = 0
    with factory() as session:
        for path in sorted(RECEIPTS_DIR.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue

            # Skip if already ingested (same merchant + datetime).
            dt_raw = data.get("datetime")
            merchant = data.get("merchant", {}).get("name", "")
            dt = _parse_dt(dt_raw)

            existing = session.execute(
                select(Receipt).where(
                    Receipt.user_id == str(user_id),
                    Receipt.merchant_name == merchant,
                    Receipt.receipt_datetime == dt,
                )
            ).scalar_one_or_none()
            if existing:
                continue

            receipt = Receipt(
                id=str(uuid.uuid4()),
                user_id=str(user_id),
                merchant_name=merchant,
                merchant_address=data.get("merchant", {}).get("address"),
                receipt_datetime=dt,
                billing_period=data.get("billing_period"),
                category=data.get("category", "other"),
                source=data.get("source", "paper"),
                currency=data.get("currency", "VND"),
                subtotal=data.get("subtotal"),
                discount=data.get("discount"),
                tax_rate=data.get("tax_rate"),
                tax_amount=data.get("tax_amount"),
                total=data.get("total", 0),
                notes=data.get("notes"),
            )
            session.add(receipt)
            session.flush()

            for item_data in data.get("items", []):
                session.add(ReceiptItem(
                    id=str(uuid.uuid4()),
                    receipt_id=receipt.id,
                    name=item_data.get("name", ""),
                    name_raw=item_data.get("name_raw"),
                    quantity=item_data.get("quantity", 1),
                    unit_price=item_data.get("unit_price"),
                    amount=item_data.get("amount", 0),
                    confidence=item_data.get("confidence", "high"),
                    toppings=item_data.get("toppings"),
                    modifiers=item_data.get("modifiers"),
                    food_tags=item_data.get("food_tags"),
                ))
            inserted += 1

        session.commit()

    return inserted


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
