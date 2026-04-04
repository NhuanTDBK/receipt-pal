"""APScheduler service for scheduled memory generation.

Manages four scheduled jobs:
- Daily memory generation (runs at configured time for previous day)
- Weekly memory generation (runs Monday at configured time for previous week)
- Monthly memory generation (runs 1st of month at configured time for previous month)
- Weekly usage report (runs Sunday at configured time for current week)
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select

from app.config import settings
from app.database import async_session_factory
from app.models.user import User
from app.repositories.memory_repo import get_memory_for_period
from app.repositories.user_settings_repo import get_users_with_weekly_reports_enabled
from app.services.memory_generator import (
    generate_daily_memory,
    generate_monthly_memory,
    generate_weekly_memory,
)
from app.services.weekly_usage_report import (
    get_current_week_start,
    get_report_for_week,
    send_weekly_report,
)

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None


def get_scheduler() -> AsyncIOScheduler:
    """Get or create the global scheduler instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler(timezone=settings.scheduler_timezone)
    return _scheduler


async def initialize_scheduler() -> None:
    """Initialize and start the scheduler with memory generation jobs."""
    if not settings.enable_scheduler:
        logger.info("Scheduler is disabled in settings")
        return

    scheduler = get_scheduler()

    # Parse schedule times
    daily_hour, daily_minute = map(int, settings.daily_memory_schedule.split(":"))
    weekly_hour, weekly_minute = map(int, settings.weekly_memory_schedule.split(":"))
    monthly_hour, monthly_minute = map(
        int, settings.monthly_memory_schedule.split(":")
    )
    report_hour, report_minute = map(int, settings.weekly_report_schedule.split(":"))

    # Daily job: runs every day at configured time for previous day
    scheduler.add_job(
        _generate_daily_memories,
        trigger=CronTrigger(hour=daily_hour, minute=daily_minute),
        id="daily_memory_generation",
        name="Daily Memory Generation",
        replace_existing=True,
    )

    # Weekly job: runs every Monday at configured time for previous week
    scheduler.add_job(
        _generate_weekly_memories,
        trigger=CronTrigger(day_of_week="mon", hour=weekly_hour, minute=weekly_minute),
        id="weekly_memory_generation",
        name="Weekly Memory Generation",
        replace_existing=True,
    )

    # Monthly job: runs 1st of month at configured time for previous month
    scheduler.add_job(
        _generate_monthly_memories,
        trigger=CronTrigger(day=1, hour=monthly_hour, minute=monthly_minute),
        id="monthly_memory_generation",
        name="Monthly Memory Generation",
        replace_existing=True,
    )

    # Weekly report job: runs every Sunday at configured time for current week
    scheduler.add_job(
        _send_weekly_reports,
        trigger=CronTrigger(day_of_week="sun", hour=report_hour, minute=report_minute),
        id="weekly_usage_report",
        name="Weekly Usage Report",
        replace_existing=True,
    )

    scheduler.start()
    logger.info(
        "Scheduler started: daily=%s, weekly=Mon %s, monthly=1st %s, report=Sun %s",
        settings.daily_memory_schedule,
        settings.weekly_memory_schedule,
        settings.monthly_memory_schedule,
        settings.weekly_report_schedule,
    )


async def shutdown_scheduler() -> None:
    """Shutdown the scheduler gracefully."""
    global _scheduler
    if _scheduler is not None:
        _scheduler.shutdown(wait=True)
        _scheduler = None
        logger.info("Scheduler shutdown")


async def _generate_daily_memories() -> None:
    """Generate daily memories for all users for the previous calendar day."""
    logger.info("Starting daily memory generation for all users")

    # Calculate yesterday's date in the configured timezone
    tz = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh (UTC+7)
    now = datetime.now(tz)
    yesterday = now - timedelta(days=1)
    yesterday_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)

    async with async_session_factory() as session:
        # Get all users
        result = await session.execute(select(User.id))
        user_ids = list(result.scalars().all())

        success_count = 0
        skip_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                # Check if memory already exists for this period
                existing = await get_memory_for_period(
                    session, user_id, "day", yesterday_date
                )
                if existing:
                    logger.debug(
                        "Daily memory already exists for user %s on %s, skipping",
                        user_id,
                        yesterday_date.date(),
                    )
                    skip_count += 1
                    continue

                # Generate daily memory
                await generate_daily_memory(session, user_id, yesterday_date)
                success_count += 1
                logger.info(
                    "Generated daily memory for user %s on %s",
                    user_id,
                    yesterday_date.date(),
                )

            except Exception as e:
                error_count += 1
                logger.error(
                    "Failed to generate daily memory for user %s on %s: %s",
                    user_id,
                    yesterday_date.date(),
                    e,
                    exc_info=True,
                )

    logger.info(
        "Daily memory generation completed: %d success, %d skipped, %d errors",
        success_count,
        skip_count,
        error_count,
    )


async def _generate_weekly_memories() -> None:
    """Generate weekly memories for all users for the previous calendar week."""
    logger.info("Starting weekly memory generation for all users")

    # Calculate previous Monday (start of previous week)
    tz = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh (UTC+7)
    now = datetime.now(tz)

    # Find Monday of the current week
    days_since_monday = now.weekday()  # Monday = 0
    current_monday = now - timedelta(days=days_since_monday)
    current_monday = current_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    # Previous week's Monday
    previous_monday = current_monday - timedelta(days=7)

    async with async_session_factory() as session:
        # Get all users
        result = await session.execute(select(User.id))
        user_ids = list(result.scalars().all())

        success_count = 0
        skip_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                # Check if memory already exists for this period
                existing = await get_memory_for_period(
                    session, user_id, "week", previous_monday
                )
                if existing:
                    logger.debug(
                        "Weekly memory already exists for user %s starting %s, skipping",
                        user_id,
                        previous_monday.date(),
                    )
                    skip_count += 1
                    continue

                # Generate weekly memory
                await generate_weekly_memory(session, user_id, previous_monday)
                success_count += 1
                logger.info(
                    "Generated weekly memory for user %s starting %s",
                    user_id,
                    previous_monday.date(),
                )

            except Exception as e:
                error_count += 1
                logger.error(
                    "Failed to generate weekly memory for user %s starting %s: %s",
                    user_id,
                    previous_monday.date(),
                    e,
                    exc_info=True,
                )

    logger.info(
        "Weekly memory generation completed: %d success, %d skipped, %d errors",
        success_count,
        skip_count,
        error_count,
    )


async def _generate_monthly_memories() -> None:
    """Generate monthly memories for all users for the previous calendar month."""
    logger.info("Starting monthly memory generation for all users")

    # Calculate 1st day of previous month
    tz = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh (UTC+7)
    now = datetime.now(tz)

    # First day of current month
    first_day_current = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # First day of previous month
    if first_day_current.month == 1:
        first_day_previous = first_day_current.replace(
            year=first_day_current.year - 1, month=12
        )
    else:
        first_day_previous = first_day_current.replace(
            month=first_day_current.month - 1
        )

    async with async_session_factory() as session:
        # Get all users
        result = await session.execute(select(User.id))
        user_ids = list(result.scalars().all())

        success_count = 0
        skip_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                # Check if memory already exists for this period
                existing = await get_memory_for_period(
                    session, user_id, "month", first_day_previous
                )
                if existing:
                    logger.debug(
                        "Monthly memory already exists for user %s in %s, skipping",
                        user_id,
                        first_day_previous.strftime("%Y-%m"),
                    )
                    skip_count += 1
                    continue

                # Generate monthly memory
                await generate_monthly_memory(session, user_id, first_day_previous)
                success_count += 1
                logger.info(
                    "Generated monthly memory for user %s in %s",
                    user_id,
                    first_day_previous.strftime("%Y-%m"),
                )

            except Exception as e:
                error_count += 1
                logger.error(
                    "Failed to generate monthly memory for user %s in %s: %s",
                    user_id,
                    first_day_previous.strftime("%Y-%m"),
                    e,
                    exc_info=True,
                )

    logger.info(
        "Monthly memory generation completed: %d success, %d skipped, %d errors",
        success_count,
        skip_count,
        error_count,
    )


async def _send_weekly_reports() -> None:
    """Send weekly usage reports to all users with reports enabled for current week."""
    logger.info("Starting weekly usage report generation for all users")

    # Get current week's Monday
    week_start = await get_current_week_start()

    async with async_session_factory() as session:
        # Get users with weekly reports enabled
        user_ids = await get_users_with_weekly_reports_enabled(session)

        success_count = 0
        skip_count = 0
        error_count = 0

        for user_id in user_ids:
            try:
                # Check if report already sent for this week
                existing = await get_report_for_week(session, str(user_id), week_start)
                if existing:
                    logger.debug(
                        "Weekly report already sent for user %s for week starting %s, skipping",
                        user_id,
                        week_start.date(),
                    )
                    skip_count += 1
                    continue

                # Get user with settings
                result = await session.execute(
                    select(User).where(User.id == user_id)
                )
                user = result.scalar_one_or_none()

                if user is None:
                    logger.warning("User %s not found, skipping", user_id)
                    skip_count += 1
                    continue

                # Get user settings for custom format/analysis
                from app.repositories.user_settings_repo import get_or_create_settings

                settings_obj = await get_or_create_settings(session, user_id)

                # Send weekly report
                await send_weekly_report(
                    session,
                    user,
                    week_start,
                    custom_format=settings_obj.weekly_report_custom_format,
                    custom_analysis=settings_obj.weekly_report_custom_analysis,
                )
                success_count += 1

            except Exception as e:
                error_count += 1
                logger.error(
                    "Failed to send weekly report for user %s for week starting %s: %s",
                    user_id,
                    week_start.date(),
                    e,
                    exc_info=True,
                )

    logger.info(
        "Weekly usage report generation completed: %d success, %d skipped, %d errors",
        success_count,
        skip_count,
        error_count,
    )