#!/usr/bin/env python3
"""Test script to verify weekly report works for previous week."""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.services.weekly_usage_report import get_current_week_start


async def main() -> None:
    """Main test function."""
    print("=" * 80)
    print("TESTING WEEKLY REPORT FOR PREVIOUS WEEK")
    print("=" * 80)
    print()

    # Create engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Get previous week's Monday (what the scheduler will use)
    week_start = await get_current_week_start(weeks_ago=1)
    week_end = week_start + timedelta(days=7)

    print(f"Testing previous week: {week_start.date()} to {week_end.date()}")
    print()

    async with async_session() as session:
        # Query receipts for previous week
        result = await session.execute(
            select(text("*"))
            .select_from(text("receipts"))
            .where(
                and_(
                    text("receipt_datetime >= :week_start"),
                    text("receipt_datetime < :week_end"),
                )
            )
            .params(week_start=week_start, week_end=week_end)
            .order_by(text("receipt_datetime DESC"))
        )
        rows = result.fetchall()

        print(f"Receipts found: {len(rows)}")
        print()

        if rows:
            print("Receipt details:")
            total_spent = 0
            for i, row in enumerate(rows, 1):
                receipt_id = row[0]
                merchant_name = row[3]
                category = row[7]
                total = row[12]
                receipt_datetime = row[5]

                total_spent += total
                print(f"{i:2d}. {receipt_datetime.date()} | {merchant_name:30s} | {category:12s} | {total:>10,} VND")
            print()

            print(f"Total spent: {total_spent:,} VND")
            print(f"Average per receipt: {total_spent // len(rows):,} VND")
            print()

            # Show category breakdown
            categories = {}
            for row in rows:
                category = row[7]
                total = row[12]
                categories[category] = categories.get(category, 0) + total

            print("Category breakdown:")
            for cat, amount in sorted(categories.items(), key=lambda x: x[1], reverse=True):
                percentage = (amount / total_spent) * 100
                print(f"  {cat.title():15s}: {amount:>10,} VND ({percentage:>5.1f}%)")
            print()

            print("✓ SUCCESS: Previous week has receipts!")
            print(f"✓ Weekly report will show {len(rows)} transactions totaling {total_spent:,} VND")
        else:
            print("✗ No receipts found for previous week")
            print()

            # Check closest receipts
            result = await session.execute(
                select(text("*"))
                .select_from(text("receipts"))
                .where(text("receipt_datetime IS NOT NULL"))
                .order_by(text("ABS(EXTRACT(EPOCH FROM (receipt_datetime - :week_start)))"))
                .limit(5)
                .params(week_start=week_start)
            )
            nearby_rows = result.fetchall()

            if nearby_rows:
                print("Closest receipts:")
                for i, row in enumerate(nearby_rows, 1):
                    receipt_dt = row[5]
                    if receipt_dt:
                        days_diff = (receipt_dt.date() - week_start.date()).days
                        print(f"{i:2d}. {receipt_dt.date()} ({days_diff:+d} days from week start)")
                        print(f"    Merchant: {row[3]}, Total: {row[12]:,} VND")

    print()
    print("=" * 80)
    print("TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())