import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings


async def get_or_create_settings(
    session: AsyncSession, user_id: uuid.UUID
) -> UserSettings:
    """Return the UserSettings row for this user, creating defaults if absent."""
    result = await session.execute(
        select(UserSettings).where(UserSettings.user_id == user_id)
    )
    settings = result.scalar_one_or_none()

    if settings is None:
        settings = UserSettings(user_id=user_id)
        session.add(settings)
        await session.commit()
        await session.refresh(settings)

    return settings


async def update_settings(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    language: str | None = None,
    response_preference: str | None = None,
    location: str | None = None,
) -> UserSettings:
    """Update only the provided setting fields. Returns the updated row."""
    settings = await get_or_create_settings(session, user_id)

    if language is not None:
        settings.language = language
    if response_preference is not None:
        settings.response_preference = response_preference
    if location is not None:
        settings.location = location

    await session.commit()
    await session.refresh(settings)
    return settings


async def update_weekly_report_settings(
    session: AsyncSession,
    user_id: uuid.UUID,
    *,
    weekly_report_enabled: bool | None = None,
    weekly_report_custom_format: str | None = None,
    weekly_report_custom_analysis: str | None = None,
) -> UserSettings:
    """Update weekly report settings. Returns the updated row."""
    settings = await get_or_create_settings(session, user_id)

    if weekly_report_enabled is not None:
        settings.weekly_report_enabled = weekly_report_enabled
    if weekly_report_custom_format is not None:
        settings.weekly_report_custom_format = weekly_report_custom_format
    if weekly_report_custom_analysis is not None:
        settings.weekly_report_custom_analysis = weekly_report_custom_analysis

    await session.commit()
    await session.refresh(settings)
    return settings


async def get_users_with_weekly_reports_enabled(
    session: AsyncSession,
) -> list[uuid.UUID]:
    """Get list of user IDs who have weekly reports enabled.

    Returns:
        List of user UUIDs
    """
    from sqlalchemy import select

    result = await session.execute(
        select(UserSettings.user_id).where(
            UserSettings.weekly_report_enabled == True  # noqa: E712
        )
    )
    return list(result.scalars().all())
