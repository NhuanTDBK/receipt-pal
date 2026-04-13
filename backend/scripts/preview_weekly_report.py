#!/usr/bin/env python3
"""Preview weekly report content without sending via Telegram."""

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
    generate_weekly_report_data,
    format_weekly_report,
    get_current_week_start,
)


async def main() -> None:
    """Main function to preview weekly report."""
    print("=" * 80)
    print("WEEKLY REPORT PREVIEW")
    print("=" * 80)
    print()

    # Create engine
    engine = create_async_engine(settings.database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Get previous week's Monday (same as scheduler)
    week_start = await get_current_week_start(weeks_ago=1)
    from datetime import timedelta
    week_end = week_start + timedelta(days=7)

    print(f"Week: {week_start.date()} to {week_end.date()}")
    print()

    async with async_session() as session:
        # Get all users
        result = await session.execute(select(User))
        users = list(result.scalars().all())

        print(f"Found {len(users)} users")
        print()

        for user in users:
            print(f"User: {user.first_name} (telegram_id={user.telegram_id})")
            print("-" * 80)

            # Generate report data
            report_data = await generate_weekly_report_data(
                session, str(user.id), week_start
            )

            # Format report (without AI insights to avoid LLM call)
            report_content = await format_weekly_report(
                report_data,
                week_start,
            )

            print(report_content)
            print()

    print("=" * 80)
    print("PREVIEW COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    asyncio.run(main())