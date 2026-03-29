"""Export receipts + items from the production PostgreSQL database into the
PoC SQLite snapshot used by ``analytics_cli.py``.

Connection parameters are read **only** from environment variables — never
hard-code credentials in this file or commit them to version control.

Quick start
-----------
    export PG_PASSWORD=<your password>
    uv run python export_pg_to_sqlite.py

Or inline:
    PG_PASSWORD=secret uv run python export_pg_to_sqlite.py --user-id <uuid>

Environment variables
---------------------
    PG_HOST      Postgres host          (default: 127.0.0.1)
    PG_PORT      Postgres port          (default: 5432)
    PG_USER      Postgres user          (default: postgres)
    PG_PASSWORD  Postgres password      (REQUIRED — no default)
    PG_DBNAME    Postgres database name (default: receipt_pal)
    POC_USER_ID  SQLite PoC user UUID   (default: 00000000-0000-0000-0000-000000000001)

Options
-------
    --user-id UUID    Export only this Postgres user UUID (overrides POC_USER_ID mapping)
    --all-users       Export every user's receipts (maps each to their own UUID in SQLite)
    --db-path PATH    SQLite file path (default: poc_receipts.db next to this script)
    --dry-run         Print counts without writing to SQLite
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

# ── Allow sibling imports ──────────────────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).resolve().parent))

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session

from db import DB_PATH
from models import Base, Receipt, ReceiptItem

# ── Default PoC user ───────────────────────────────────────────────────────────
_DEFAULT_POC_USER = "00000000-0000-0000-0000-000000000001"


# ─────────────────────────────────────────────────────────────────────────────
# PostgreSQL helpers
# ─────────────────────────────────────────────────────────────────────────────


def _pg_url() -> str:
    host = os.environ.get("PG_HOST", "127.0.0.1")
    port = os.environ.get("PG_PORT", "5432")
    user = os.environ.get("PG_USER", "postgres")
    dbname = os.environ.get("PG_DBNAME", "receipt_pal")
    password = os.environ.get("PG_PASSWORD", "")
    if not password:
        print("ERROR: PG_PASSWORD env var is not set.")
        print("  export PG_PASSWORD=<your password>  and re-run.")
        sys.exit(1)
    return f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"


def _fetch_user_ids(pg_session: Session, target_id: str | None) -> list[str]:
    """Return the list of Postgres user UUIDs to export."""
    if target_id:
        return [target_id]
    rows = pg_session.execute(
        text("SELECT id FROM users ORDER BY created_at")
    ).fetchall()
    return [str(r[0]) for r in rows]


def _fetch_receipts(pg_session: Session, pg_user_id: str) -> list[dict[str, Any]]:
    sql = text("""
        SELECT
            id::text,
            user_id::text,
            merchant_name,
            merchant_address,
            receipt_datetime,
            billing_period,
            category,
            source,
            currency,
            subtotal,
            discount,
            tax_rate,
            tax_amount,
            total,
            notes,
            created_at
        FROM receipts
        WHERE user_id = :uid
        ORDER BY receipt_datetime DESC NULLS LAST
    """)
    rows = pg_session.execute(sql, {"uid": pg_user_id}).mappings().fetchall()
    return [dict(r) for r in rows]


def _fetch_items(pg_session: Session, receipt_id: str) -> list[dict[str, Any]]:
    sql = text("""
        SELECT
            id::text,
            receipt_id::text,
            name,
            name_raw,
            quantity,
            unit_price,
            amount,
            confidence,
            toppings,
            modifiers,
            food_tags
        FROM receipt_items
        WHERE receipt_id = :rid
        ORDER BY id
    """)
    rows = pg_session.execute(sql, {"rid": receipt_id}).mappings().fetchall()
    return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# SQLite helpers
# ─────────────────────────────────────────────────────────────────────────────


def _jsonb_to_py(value: Any) -> Any:
    """psycopg2 returns JSONB as Python objects already; normalise edge cases."""
    if value is None:
        return None
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return value
    return value


def _upsert_receipt(
    sqlite_session: Session,
    pg_row: dict[str, Any],
    sqlite_user_id: str,
    dry_run: bool,
) -> bool:
    """Insert (or re-map) one PG receipt into SQLite.  Returns True if inserted/updated, False if skipped."""
    pg_id = pg_row["id"]

    existing = sqlite_session.get(Receipt, pg_id)
    if existing:
        # Re-map to correct POC user_id if it ended up under the wrong one.
        if existing.user_id != sqlite_user_id:
            if not dry_run:
                existing.user_id = sqlite_user_id
            return True
        return False  # already present and correct

    if dry_run:
        return True

    receipt = Receipt(
        id=pg_id,
        user_id=sqlite_user_id,
        merchant_name=pg_row["merchant_name"],
        merchant_address=pg_row.get("merchant_address"),
        receipt_datetime=pg_row.get("receipt_datetime"),
        billing_period=pg_row.get("billing_period"),
        category=pg_row.get("category", "other"),
        source=pg_row.get("source", "paper"),
        currency=pg_row.get("currency", "VND"),
        subtotal=pg_row.get("subtotal"),
        discount=pg_row.get("discount"),
        tax_rate=pg_row.get("tax_rate"),
        tax_amount=pg_row.get("tax_amount"),
        total=pg_row.get("total", 0),
        notes=pg_row.get("notes"),
    )
    sqlite_session.add(receipt)
    return True


def _upsert_items(
    sqlite_session: Session,
    items: list[dict[str, Any]],
    dry_run: bool,
) -> int:
    inserted = 0
    for item in items:
        existing = sqlite_session.get(ReceiptItem, item["id"])
        if existing:
            continue
        if not dry_run:
            sqlite_session.add(
                ReceiptItem(
                    id=item["id"],
                    receipt_id=item["receipt_id"],
                    name=item["name"],
                    name_raw=item.get("name_raw"),
                    quantity=item.get("quantity", 1),
                    unit_price=item.get("unit_price"),
                    amount=item.get("amount", 0),
                    confidence=item.get("confidence", "high"),
                    toppings=_jsonb_to_py(item.get("toppings")),
                    modifiers=_jsonb_to_py(item.get("modifiers")),
                    food_tags=_jsonb_to_py(item.get("food_tags")),
                )
            )
        inserted += 1
    return inserted


# ─────────────────────────────────────────────────────────────────────────────
# Main export logic
# ─────────────────────────────────────────────────────────────────────────────


def run_export(
    target_pg_user_id: str | None,
    all_users: bool,
    sqlite_path: Path,
    dry_run: bool,
) -> None:
    poc_user_id = os.environ.get("POC_USER_ID", _DEFAULT_POC_USER)

    # ── Postgres connection ────────────────────────────────────────────────────
    print("  Connecting to PostgreSQL …")
    pg_engine = create_engine(_pg_url(), echo=False)
    PgSession = sessionmaker(pg_engine, expire_on_commit=False)

    # ── SQLite connection ──────────────────────────────────────────────────────
    print(f"  Opening SQLite at {sqlite_path} …")
    sqlite_engine = create_engine(f"sqlite:///{sqlite_path}", echo=False)
    Base.metadata.create_all(sqlite_engine)
    SqliteSession = sessionmaker(sqlite_engine, expire_on_commit=False)

    dry_tag = "  [DRY RUN] " if dry_run else "  "

    with PgSession() as pg_session:
        pg_user_ids = _fetch_user_ids(pg_session, target_pg_user_id)
        print(f"  Found {len(pg_user_ids)} Postgres user(s) to export.")
        print()

        total_receipts = 0
        total_items = 0

        for pg_uid in pg_user_ids:
            # Map every PG user → the same SQLite PoC user (single-user PoC),
            # unless exporting all users (each keeps their own UUID in SQLite).
            sqlite_uid = pg_uid if all_users else poc_user_id

            receipts = _fetch_receipts(pg_session, pg_uid)
            print(f"  User {pg_uid}  →  {len(receipts)} receipt(s)")

            with SqliteSession() as sqlite_session:
                inserted_r = 0
                inserted_i = 0

                for pg_receipt in receipts:
                    inserted = _upsert_receipt(
                        sqlite_session, pg_receipt, sqlite_uid, dry_run
                    )
                    if inserted:
                        inserted_r += 1
                        items = _fetch_items(pg_session, pg_receipt["id"])
                        inserted_i += _upsert_items(sqlite_session, items, dry_run)

                if not dry_run:
                    sqlite_session.commit()

                skipped_r = len(receipts) - inserted_r
                print(
                    f"{dry_tag}  → inserted {inserted_r} receipt(s), "
                    f"{inserted_i} item(s)"
                    + (f"  (skipped {skipped_r} already present)" if skipped_r else "")
                )
                total_receipts += inserted_r
                total_items += inserted_i

    print()
    if dry_run:
        print(
            f"  DRY RUN complete — would insert {total_receipts} receipt(s) and {total_items} item(s)."
        )
    else:
        print(
            f"  ✅ Export complete — {total_receipts} receipt(s), {total_items} item(s) written to {sqlite_path}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Export PostgreSQL receipts → PoC SQLite snapshot",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    user_group = p.add_mutually_exclusive_group()
    user_group.add_argument(
        "--user-id",
        metavar="UUID",
        help="Export only this Postgres user UUID (maps to POC_USER_ID in SQLite).",
    )
    user_group.add_argument(
        "--all-users",
        action="store_true",
        default=False,
        help="Export all users (each keeps their own UUID in SQLite).",
    )
    p.add_argument(
        "--db-path",
        metavar="PATH",
        default=str(DB_PATH),
        help=f"SQLite output path (default: {DB_PATH})",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print what would be inserted without writing anything.",
    )
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    print()
    print("  ┌─────────────────────────────────────────────┐")
    print("  │   Receipt-Pal  PG → SQLite Snapshot Export  │")
    print("  └─────────────────────────────────────────────┘")
    print()
    run_export(
        target_pg_user_id=args.user_id,
        all_users=args.all_users,
        sqlite_path=Path(args.db_path),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
