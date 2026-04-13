#!/usr/bin/env python3
"""Resend weekly report by deleting existing report first."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.user import User
from app.models.weekly_usage_report import WeeklyUsageReport
from app.services.weekly_usage_report import (
    send_weekly_report,
    get_current_week_start,
)
from app.presentation.bot.bot import get_bot_manager


async def main() -> None:
    """Main function to resend weekly report."""
    print("=" * 80)
    print("RESEND WEEKLY REPORT")
    print("=" * 80)
    print()

    # Initialize bot manager
    print("Initializing bot manager...")
    bot_manager = get_bot_manager()
    await bot_manager.initialize()
    print("✓ Bot manager initialized")
    print()

    # Create engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Get previous week's Monday (same as scheduler)
    week_start = await get_current_week_start(weeks_ago=1)
    from datetime import timedelta
    week_end = week_start + timedelta(days=7)

    print(f"Resending report for week: {week_start.date()} to {week_end.date()}")
    print()

    async with async_session() as session:
        # Get all users
        result = await session.execute(select(User))
        users = list(result.scalars().all())

        print(f"Found {len(users)} users")
        print()

        for user in users:
            print(f"User: {user.first_name} (telegram_id={user.telegram_id})")

            # Check if report exists
            existing = await session.execute(
                select(WeeklyUsageReport).where(
                    WeeklyUsageReport.user_id == user.id,
                    WeeklyUsageReport.week_start == week_start,
                )
            )
            existing_report = existing.scalar_one_or_none()

            if existing_report:
                print(f"  Deleting existing report (id={existing_report.id})...")
                await session.delete(existing_report)
                await session.commit()
                print(f"  ✓ Existing report deleted")
            else:
                print(f"  No existing report found")

            # Send new report
            print(f"  Sending new report...")
            try:
                report = await send_weekly_report(
                    session,
                    user,
                    week_start,
                )
                print(f"  ✓ Report sent successfully (report_id={report.id})")
                print(f"  Report preview (first 500 chars):")
                print(f"  {report.report_content[:500]}...")
            except Exception as e:
                print(f"  ✗ Failed to send report: {e}")
                import traceback
                traceback.print_exc()
            print()

    print("=" * 80)
    print("RESEND COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())