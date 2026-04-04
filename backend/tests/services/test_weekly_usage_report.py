"""Unit tests for weekly usage report service."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.receipt import Receipt, ReceiptItem
from app.models.user import User
from app.models.weekly_usage_report import WeeklyUsageReport
from app.services.weekly_usage_report import (
    format_weekly_report,
    generate_weekly_report_data,
    get_current_week_start,
    get_report_for_week,
    send_weekly_report,
)


@pytest.mark.asyncio
async def test_generate_weekly_report_data_empty(db_session: AsyncSession) -> None:
    """Test report data generation when no receipts exist."""
    user_id = uuid.uuid4()
    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = await generate_weekly_report_data(db_session, str(user_id), week_start)

    assert result["receipt_count"] == 0
    assert result["total_spent"] == 0
    assert result["largest_expense"] == 0
    assert result["largest_merchant"] == "N/A"
    assert result["category_breakdown"] == []
    assert result["top_merchants"] == []
    assert result["top_items"] == []


@pytest.mark.asyncio
async def test_generate_weekly_report_data_with_receipts(
    db_session: AsyncSession,
) -> None:
    """Test report data generation with sample receipts."""
    user = User(id=uuid.uuid4(), telegram_id=123, first_name="Test")
    db_session.add(user)
    await db_session.flush()

    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Create receipts
    receipt1 = Receipt(
        id=uuid.uuid4(),
        user_id=user.id,
        merchant_name="Starbucks",
        category="food",
        total=50000,
        receipt_datetime=week_start + timedelta(hours=1),
    )
    receipt2 = Receipt(
        id=uuid.uuid4(),
        user_id=user.id,
        merchant_name="Pho 24",
        category="food",
        total=80000,
        receipt_datetime=week_start + timedelta(hours=2),
    )
    receipt3 = Receipt(
        id=uuid.uuid4(),
        user_id=user.id,
        merchant_name="Grab",
        category="transport",
        total=30000,
        receipt_datetime=week_start + timedelta(hours=3),
    )
    db_session.add_all([receipt1, receipt2, receipt3])

    # Add items
    item1 = ReceiptItem(
        id=uuid.uuid4(),
        receipt_id=receipt1.id,
        name="Iced Coffee",
        quantity=2,
        amount=50000,
    )
    item2 = ReceiptItem(
        id=uuid.uuid4(),
        receipt_id=receipt2.id,
        name="Beef Pho",
        quantity=1,
        amount=80000,
    )
    db_session.add_all([item1, item2])

    result = await generate_weekly_report_data(db_session, str(user.id), week_start)

    assert result["receipt_count"] == 3
    assert result["total_spent"] == 160000
    assert result["largest_expense"] == 80000
    assert result["largest_merchant"] == "Pho 24"
    assert len(result["category_breakdown"]) == 2
    assert result["category_breakdown"][0]["category"] == "food"
    assert result["category_breakdown"][0]["spent"] == 130000
    assert result["category_breakdown"][1]["category"] == "transport"
    assert result["category_breakdown"][1]["spent"] == 30000
    assert len(result["top_items"]) == 2
    assert result["top_items"][0]["item"] == "Iced Coffee"
    assert result["top_items"][0]["count"] == 2


@pytest.mark.asyncio
async def test_format_weekly_report_default(db_session: AsyncSession) -> None:
    """Test report formatting with default template."""
    report_data = {
        "receipt_count": 3,
        "total_spent": 160000,
        "largest_expense": 80000,
        "largest_merchant": "Pho 24",
        "category_breakdown": [
            {"category": "food", "spent": 130000},
            {"category": "transport", "spent": 30000},
        ],
    }
    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Mock AI insights to avoid actual LLM call
    with patch(
        "app.services.weekly_usage_report._generate_ai_insights",
        return_value="You spent most on food this week.",
    ):
        report = await format_weekly_report(report_data, week_start)

    assert "📊 <b>Weekly Spending Report</b>" in report
    assert "160,000 VND" in report
    assert "80,000 VND" in report
    assert "Pho 24" in report
    assert "Food: 130,000 VND" in report
    assert "Transport: 30,000 VND" in report


@pytest.mark.asyncio
async def test_format_weekly_report_custom_format(db_session: AsyncSession) -> None:
    """Test report formatting with custom format."""
    report_data = {
        "receipt_count": 3,
        "total_spent": 160000,
        "largest_expense": 80000,
        "largest_merchant": "Pho 24",
        "category_breakdown": [
            {"category": "food", "spent": 130000},
        ],
    }
    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    custom_format = "Custom Report: {total_spent} VND spent on {receipt_count} transactions."

    with patch(
        "app.services.weekly_usage_report._generate_ai_insights",
        return_value="",
    ):
        report = await format_weekly_report(
            report_data, week_start, custom_format=custom_format
        )

    assert "Custom Report: 160000 VND spent on 3 transactions." in report


@pytest.mark.asyncio
async def test_get_current_week_start() -> None:
    """Test getting current week's Monday."""
    week_start = await get_current_week_start()

    assert week_start.weekday() == 0  # Monday
    assert week_start.hour == 0
    assert week_start.minute == 0
    assert week_start.second == 0
    assert week_start.microsecond == 0


@pytest.mark.asyncio
async def test_get_report_for_week_not_found(db_session: AsyncSession) -> None:
    """Test checking for report when none exists."""
    user_id = uuid.uuid4()
    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    result = await get_report_for_week(db_session, str(user_id), week_start)

    assert result is None


@pytest.mark.asyncio
async def test_get_report_for_week_found(db_session: AsyncSession) -> None:
    """Test checking for report when one exists."""
    user = User(id=uuid.uuid4(), telegram_id=123, first_name="Test")
    db_session.add(user)
    await db_session.flush()

    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Create a report
    report = WeeklyUsageReport(
        user_id=user.id,
        week_start=week_start,
        report_content="Test report",
    )
    db_session.add(report)
    await db_session.commit()

    result = await get_report_for_week(db_session, str(user.id), week_start)

    assert result is not None
    assert result.id == report.id
    assert result.report_content == "Test report"


@pytest.mark.asyncio
async def test_send_weekly_report(db_session: AsyncSession) -> None:
    """Test sending weekly report to user."""
    user = User(id=uuid.uuid4(), telegram_id=123, first_name="Test")
    db_session.add(user)
    await db_session.flush()

    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    # Mock bot manager
    mock_bot_manager = MagicMock()
    mock_bot_manager.send_message = AsyncMock()

    with patch(
        "app.services.weekly_usage_report.get_bot_manager",
        return_value=mock_bot_manager,
    ), patch(
        "app.services.weekly_usage_report._generate_ai_insights",
        return_value="",
    ):
        report = await send_weekly_report(db_session, user, week_start)

    # Verify report was created
    assert report.user_id == user.id
    assert report.week_start == week_start
    assert report.report_content is not None

    # Verify message was sent
    mock_bot_manager.send_message.assert_called_once()
    call_args = mock_bot_manager.send_message.call_args
    assert call_args[1]["chat_id"] == 123
    assert "Weekly Spending Report" in call_args[1]["text"]

    # Verify report is in database
    result = await db_session.execute(
        select(WeeklyUsageReport).where(WeeklyUsageReport.id == report.id)
    )
    db_report = result.scalar_one_or_none()
    assert db_report is not None
    assert db_report.user_id == user.id


@pytest.mark.asyncio
async def test_send_weekly_report_with_custom_settings(db_session: AsyncSession) -> None:
    """Test sending weekly report with custom format and analysis."""
    from app.repositories.user_settings_repo import get_or_create_settings

    user = User(id=uuid.uuid4(), telegram_id=123, first_name="Test")
    db_session.add(user)
    await db_session.flush()

    # Set custom settings
    settings = await get_or_create_settings(db_session, user.id)
    settings.weekly_report_custom_format = "Custom: {total_spent} VND"
    settings.weekly_report_custom_analysis = "Analyze this spending."
    await db_session.commit()

    week_start = datetime.now(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    mock_bot_manager = MagicMock()
    mock_bot_manager.send_message = AsyncMock()

    with patch(
        "app.services.weekly_usage_report.get_bot_manager",
        return_value=mock_bot_manager,
    ), patch(
        "app.services.weekly_usage_report._generate_ai_insights",
        return_value="Custom insight.",
    ):
        report = await send_weekly_report(db_session, user, week_start)

    # Verify custom format was used
    assert "Custom:" in report.report_content
    mock_bot_manager.send_message.assert_called_once()