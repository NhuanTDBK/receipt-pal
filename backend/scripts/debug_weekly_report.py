#!/usr/bin/env python3
"""Debug script to investigate weekly report issues on remote database.

This script connects to the database and investigates:
1. Total receipts count
2. Receipts with NULL receipt_datetime
3. Timezone and values of receipt_datetime
4. Current week_start calculation
5. What receipts would be returned for the weekly report query
"""

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import and_, func, select, text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings


async def main() -> None:
    """Main debugging function."""
    print("=" * 80)
    print("WEEKLY REPORT DEBUGGING")
    print("=" * 80)
    print()

    # Create engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 1. Check total receipts count
        print("1. TOTAL RECEIPTS COUNT")
        print("-" * 80)
        result = await session.execute(select(func.count()).select_from(text("receipts")))
        total_count = result.scalar()
        print(f"   Total receipts in database: {total_count}")
        print()

        # 2. Check receipts with NULL receipt_datetime
        print("2. RECEIPTS WITH NULL receipt_datetime")
        print("-" * 80)
        result = await session.execute(
            select(func.count())
            .select_from(text("receipts"))
            .where(text("receipt_datetime IS NULL"))
        )
        null_count = result.scalar()
        print(f"   Receipts with NULL receipt_datetime: {null_count}")
        print(f"   Percentage: {(null_count / total_count * 100):.1f}%" if total_count > 0 else "   N/A")
        print()

        # 3. Check receipts with non-NULL receipt_datetime
        print("3. RECEIPTS WITH NON-NULL receipt_datetime")
        print("-" * 80)
        result = await session.execute(
            select(text("receipt_datetime, created_at"))
            .select_from(text("receipts"))
            .where(text("receipt_datetime IS NOT NULL"))
            .order_by(text("receipt_datetime DESC"))
            .limit(10)
        )
        rows = result.fetchall()
        print(f"   Sample of 10 most recent receipt_datetime values:")
        for i, (receipt_dt, created_at) in enumerate(rows, 1):
            receipt_str = receipt_dt.isoformat() if receipt_dt else "NULL"
            created_str = created_at.isoformat() if created_at else "NULL"
            print(f"   {i:2d}. receipt_datetime: {receipt_str}")
            print(f"       created_at:        {created_str}")
            if receipt_dt:
                print(f"       timezone:          {receipt_dt.tzinfo}")
        print()

        # 4. Check date range of receipts
        print("4. DATE RANGE OF RECEIPTS")
        print("-" * 80)
        result = await session.execute(
            select(
                func.min(text("receipt_datetime")),
                func.max(text("receipt_datetime")),
            )
            .select_from(text("receipts"))
            .where(text("receipt_datetime IS NOT NULL"))
        )
        min_dt, max_dt = result.fetchone()
        print(f"   Earliest receipt_datetime: {min_dt.isoformat() if min_dt else 'N/A'}")
        print(f"   Latest receipt_datetime:   {max_dt.isoformat() if max_dt else 'N/A'}")
        if min_dt and max_dt:
            days_span = (max_dt - min_dt).days
            print(f"   Span: {days_span} days")
        print()

        # 5. Check current week_start calculation
        print("5. CURRENT WEEK_START CALCULATION")
        print("-" * 80)
        tz = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh (UTC+7)
        now = datetime.now(tz)
        days_since_monday = now.weekday()  # Monday = 0
        current_monday = now - timedelta(days=days_since_monday)
        week_start = current_monday.replace(hour=0, minute=0, second=0, microsecond=0)
        week_end = week_start + timedelta(days=7)

        print(f"   Current time (UTC+7):       {now.isoformat()}")
        print(f"   Days since Monday:          {days_since_monday}")
        print(f"   Week start (Monday):        {week_start.isoformat()}")
        print(f"   Week end (next Monday):     {week_end.isoformat()}")
        print()

        # 6. Run the actual weekly report query
        print("6. WEEKLY REPORT QUERY RESULTS")
        print("-" * 80)
        print(f"   Querying receipts for week: {week_start.date()} to {week_end.date()}")
        print()

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
        print(f"   Receipts found: {len(rows)}")
        print()

        if rows:
            print("   Receipt details:")
            for i, row in enumerate(rows, 1):
                print(f"   {i:2d}. ID: {row[0]}")
                print(f"       Merchant: {row[3]}")
                print(f"       Total: {row[12]:,} VND")
                print(f"       receipt_datetime: {row[5].isoformat() if row[5] else 'NULL'}")
                print(f"       created_at: {row[14].isoformat() if row[14] else 'NULL'}")
                print()
        else:
            print("   No receipts found for this week!")
            print()

            # Try to find the closest receipts
            print("   Looking for receipts around this week...")
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
                print("   Closest receipts:")
                for i, row in enumerate(nearby_rows, 1):
                    receipt_dt = row[5]
                    if receipt_dt:
                        days_diff = (receipt_dt.date() - week_start.date()).days
                        print(f"   {i:2d}. {receipt_dt.date()} ({days_diff:+d} days from week start)")
                        print(f"       Merchant: {row[3]}, Total: {row[12]:,} VND")
                print()

        # 7. Check if there are any receipts this year
        print("7. RECEIPTS IN 2026")
        print("-" * 80)
        result = await session.execute(
            select(func.count())
            .select_from(text("receipts"))
            .where(text("receipt_datetime >= '2026-01-01'"))
        )
        count_2026 = result.scalar()
        print(f"   Receipts in 2026: {count_2026}")
        print()

        # 8. Summary
        print("8. SUMMARY")
        print("-" * 80)
        print(f"   Total receipts: {total_count}")
        print(f"   NULL receipt_datetime: {null_count}")
        print(f"   Non-NULL receipt_datetime: {total_count - null_count}")
        print(f"   Current week: {week_start.date()} to {week_end.date()}")
        print(f"   Receipts in current week: {len(rows)}")
        print()

        if null_count > 0:
            print("   ⚠️  ISSUE FOUND: Some receipts have NULL receipt_datetime")
            print("   → These receipts are excluded from weekly report queries")
            print()

        if len(rows) == 0 and (total_count - null_count) > 0:
            print("   ⚠️  ISSUE FOUND: No receipts found for current week")
            print("   → Possible causes:")
            print("     1. Receipts are from a different time period")
            print("     2. Timezone mismatch in receipt_datetime values")
            print("     3. Week calculation is incorrect")
            print()

        if count_2026 == 0:
            print("   ⚠️  ISSUE FOUND: No receipts in 2026")
            print("   → All receipts might be from previous years")
            print()

    print("=" * 80)
    print("DEBUGGING COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())