#!/usr/bin/env python3
"""Backfill script to populate NULL receipt_datetime values.

Uses conversation.started_at as primary strategy, with billing_period as fallback.
"""

import asyncio
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.receipt import Receipt


async def backfill_receipt_datetime() -> None:
    """Backfill NULL receipt_datetime values."""
    print("=" * 80)
    print("BACKFILLING NULL receipt_datetime VALUES")
    print("=" * 80)
    print()

    # Create engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get receipts with NULL receipt_datetime
        result = await session.execute(
            select(text("*"))
            .select_from(text("receipts"))
            .where(text("receipt_datetime IS NULL"))
        )
        rows = result.fetchall()

        if not rows:
            print("No receipts with NULL receipt_datetime found. Nothing to do.")
            return

        print(f"Found {len(rows)} receipts with NULL receipt_datetime")
        print()

        updated_count = 0
        skipped_count = 0

        for i, row in enumerate(rows, 1):
            receipt_id = row[0]
            conversation_id = row[2]
            merchant_name = row[3]
            billing_period = row[6]
            category = row[7]

            print(f"{i}. Processing: {merchant_name}")

            # Strategy 1: Use conversation.started_at
            if conversation_id:
                result2 = await session.execute(
                    select(text("started_at"))
                    .select_from(text("conversations"))
                    .where(text("id = :conv_id"))
                    .params(conv_id=conversation_id)
                )
                conv_started = result2.scalar()

                if conv_started:
                    print(f"   Using conversation.started_at: {conv_started.isoformat()}")
                    await session.execute(
                        update(Receipt)
                        .where(Receipt.id == receipt_id)
                        .values(receipt_datetime=conv_started)
                    )
                    updated_count += 1
                    print(f"   ✓ Updated")
                    print()
                    continue

            # Strategy 2: Use billing_period (first day of month at noon)
            if billing_period:
                try:
                    year, month = map(int, billing_period.split("-"))
                    estimated_dt = datetime(year, month, 1, 12, 0, 0)
                    print(f"   Using billing_period: {billing_period} → {estimated_dt.isoformat()}")
                    await session.execute(
                        update(Receipt)
                        .where(Receipt.id == receipt_id)
                        .values(receipt_datetime=estimated_dt)
                    )
                    updated_count += 1
                    print(f"   ✓ Updated")
                    print()
                    continue
                except (ValueError, TypeError) as e:
                    print(f"   ✗ Failed to parse billing_period: {e}")

            # No strategy worked
            print(f"   ✗ Skipped (no conversation.started_at or billing_period)")
            skipped_count += 1
            print()

        # Commit changes
        await session.commit()

        print("=" * 80)
        print("BACKFILL SUMMARY")
        print("=" * 80)
        print(f"Total receipts processed: {len(rows)}")
        print(f"Updated: {updated_count}")
        print(f"Skipped: {skipped_count}")
        print()

        if updated_count > 0:
            print("✓ Backfill completed successfully!")

            # Verify the backfill
            result = await session.execute(
                select(text("COUNT(*)"))
                .select_from(text("receipts"))
                .where(text("receipt_datetime IS NULL"))
            )
            remaining_null = result.scalar()
            print(f"Remaining NULL receipt_datetime: {remaining_null}")
        else:
            print("✗ No receipts were updated")


if __name__ == "__main__":
    asyncio.run(backfill_receipt_datetime())