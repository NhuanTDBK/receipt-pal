#!/usr/bin/env python3
"""Manual script to trigger weekly report for testing."""

import asyncio
import sys
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.models.user import User
from app.services.weekly_usage_report import (
    send_weekly_report,
    get_current_week_start,
)
from app.presentation.bot.bot import get_bot_manager


async def main() -> None:
    """Main function to manually send weekly report."""
    print("=" * 80)
    print("MANUAL WEEKLY REPORT TRIGGER")
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

    print(f"Sending report for week: {week_start.date()} to {week_end.date()}")
    print()

    async with async_session() as session:
        # Get all users
        result = await session.execute(select(User))
        users = list(result.scalars().all())

        print(f"Found {len(users)} users")
        print()

        for user in users:
            print(f"Sending report to user: {user.first_name} (telegram_id={user.telegram_id})")
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
    print("MANUAL REPORT TRIGGER COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())