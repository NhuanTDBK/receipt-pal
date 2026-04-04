"""Weekly usage report service for scheduled user spending insights.

Generates and sends weekly spending reports to users via Telegram.
Reports include General stats (total spending, largest spending) and
Detail breakdown (spending by category), with support for user customization.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from openai import AsyncOpenAI
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.receipt import Receipt
from app.models.user import User
from app.models.weekly_usage_report import WeeklyUsageReport
from app.presentation.bot.bot import get_bot_manager

logger = logging.getLogger(__name__)

_DEFAULT_REPORT_TEMPLATE = """📊 **Weekly Spending Report**
{week_range}

📈 **General**
• Total spending: {total_spent:,} VND
• Largest expense: {largest_expense:,} VND ({largest_merchant})
• Number of transactions: {receipt_count}

📋 **Detail by Category**
{category_breakdown}

{ai_insights}
"""

_AI_INSIGHTS_PROMPT = """You are a personal spending analyst. Analyze the following weekly spending data and provide 2-3 concise, actionable insights.

## Weekly Spending Data
- Total spent: {total_spent:,} VND
- Number of transactions: {receipt_count}
- Top category: {top_category} ({top_category_spent:,} VND)
- Top merchant: {top_merchant} ({top_merchant_spent:,} VND)
- Category breakdown:
{category_details}

## Your Task
Provide 2-3 concise insights about:
1. Spending patterns or trends
2. Notable categories or merchants
3. Any recommendations or observations

Keep it brief (under 150 words), friendly, and actionable. Respond in plain text only, no markdown.
"""


async def generate_weekly_report_data(
    session: AsyncSession, user_id: str, week_start: datetime
) -> dict[str, Any]:
    """Generate weekly spending report data for a user.

    Args:
        session: Database session
        user_id: User UUID
        week_start: Monday of the week (timezone-aware)

    Returns:
        Dictionary with report data including total_spent, largest_expense,
        category_breakdown, etc.
    """
    week_end = week_start + timedelta(days=7)

    # Get receipts for the week
    result = await session.execute(
        select(Receipt)
        .where(
            and_(
                Receipt.user_id == user_id,
                Receipt.receipt_datetime >= week_start,
                Receipt.receipt_datetime < week_end,
            )
        )
        .options(selectinload(Receipt.items))
        .order_by(Receipt.receipt_datetime.desc())
    )
    receipts = list(result.scalars().all())

    if not receipts:
        return {
            "receipt_count": 0,
            "total_spent": 0,
            "largest_expense": 0,
            "largest_merchant": "N/A",
            "category_breakdown": [],
            "top_merchants": [],
            "top_items": [],
        }

    # Calculate totals
    total_spent = sum(r.total for r in receipts)
    receipt_count = len(receipts)

    # Find largest expense
    largest_receipt = max(receipts, key=lambda r: r.total)
    largest_expense = largest_receipt.total
    largest_merchant = largest_receipt.merchant_name

    # Category breakdown
    category_spend: dict[str, int] = {}
    for r in receipts:
        category_spend[r.category] = category_spend.get(r.category, 0) + r.total

    category_breakdown = [
        {"category": cat, "spent": amount}
        for cat, amount in sorted(
            category_spend.items(), key=lambda x: x[1], reverse=True
        )
    ]

    # Top merchants
    merchant_spend: dict[str, int] = {}
    for r in receipts:
        merchant_spend[r.merchant_name] = (
            merchant_spend.get(r.merchant_name, 0) + r.total
        )

    top_merchants = [
        {"merchant": merch, "spent": amount}
        for merch, amount in sorted(
            merchant_spend.items(), key=lambda x: x[1], reverse=True
        )[:5]
    ]

    # Top items
    item_counts: dict[str, int] = {}
    for r in receipts:
        for item in r.items:
            item_counts[item.name] = item_counts.get(item.name, 0) + item.quantity

    top_items = [
        {"item": item, "count": count}
        for item, count in sorted(
            item_counts.items(), key=lambda x: x[1], reverse=True
        )[:5]
    ]

    return {
        "receipt_count": receipt_count,
        "total_spent": total_spent,
        "largest_expense": largest_expense,
        "largest_merchant": largest_merchant,
        "category_breakdown": category_breakdown,
        "top_merchants": top_merchants,
        "top_items": top_items,
    }


async def format_weekly_report(
    report_data: dict[str, Any],
    week_start: datetime,
    custom_format: str | None = None,
    custom_analysis: str | None = None,
) -> str:
    """Format weekly spending report as a message.

    Args:
        report_data: Report data from generate_weekly_report_data()
        week_start: Monday of the week
        custom_format: Optional custom formatting instructions
        custom_analysis: Optional custom AI analysis prompts

    Returns:
        Formatted report message as HTML string
    """
    week_end = week_start + timedelta(days=7)
    week_range = f"{week_start.strftime('%b %d')} - {week_end.strftime('%b %d')}"

    # Format category breakdown
    category_lines = []
    for cat in report_data["category_breakdown"]:
        percentage = (
            (cat["spent"] / report_data["total_spent"]) * 100
            if report_data["total_spent"] > 0
            else 0
        )
        category_lines.append(
            f"• {cat['category'].title()}: {cat['spent']:,} VND ({percentage:.1f}%)"
        )
    category_breakdown = "\n".join(category_lines) if category_lines else "No spending this week"

    # Generate AI insights if there's spending
    ai_insights = ""
    if report_data["total_spent"] > 0:
        ai_insights = await _generate_ai_insights(
            report_data, custom_analysis or _AI_INSIGHTS_PROMPT
        )
        if ai_insights:
            ai_insights = f"\n**💡 Insights**\n{ai_insights}"

    # Use custom format if provided, otherwise use default template
    if custom_format:
        # Simple variable substitution for custom format
        formatted = custom_format.format(
            week_range=week_range,
            total_spent=report_data["total_spent"],
            largest_expense=report_data["largest_expense"],
            largest_merchant=report_data["largest_merchant"],
            receipt_count=report_data["receipt_count"],
            category_breakdown=category_breakdown,
            ai_insights=ai_insights,
        )
        return formatted
    else:
        return _DEFAULT_REPORT_TEMPLATE.format(
            week_range=week_range,
            total_spent=report_data["total_spent"],
            largest_expense=report_data["largest_expense"],
            largest_merchant=report_data["largest_merchant"],
            receipt_count=report_data["receipt_count"],
            category_breakdown=category_breakdown,
            ai_insights=ai_insights,
        )


async def _generate_ai_insights(
    report_data: dict[str, Any], prompt_template: str
) -> str:
    """Generate AI-powered insights for the weekly report.

    Args:
        report_data: Report data from generate_weekly_report_data()
        prompt_template: Prompt template to use (can be custom or default)

    Returns:
        AI-generated insights as plain text
    """
    # Format category details for the prompt
    category_details = "\n".join(
        f"- {cat['category']}: {cat['spent']:,} VND"
        for cat in report_data["category_breakdown"]
    )

    # Get top category and merchant
    top_category = (
        report_data["category_breakdown"][0]["category"]
        if report_data["category_breakdown"]
        else "N/A"
    )
    top_category_spent = (
        report_data["category_breakdown"][0]["spent"]
        if report_data["category_breakdown"]
        else 0
    )
    top_merchant = (
        report_data["top_merchants"][0]["merchant"]
        if report_data["top_merchants"]
        else "N/A"
    )
    top_merchant_spent = (
        report_data["top_merchants"][0]["spent"] if report_data["top_merchants"] else 0
    )

    prompt = prompt_template.format(
        total_spent=report_data["total_spent"],
        receipt_count=report_data["receipt_count"],
        top_category=top_category,
        top_category_spent=top_category_spent,
        top_merchant=top_merchant,
        top_merchant_spent=top_merchant_spent,
        category_details=category_details,
    )

    try:
        client = AsyncOpenAI(
            api_key=settings.openai_api_key,
            base_url=settings.openai_base_url,
        )

        response = await client.chat.completions.create(
            model=settings.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a personal spending analyst.",
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=200,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error("Failed to generate AI insights: %s", e)
        return ""


async def send_weekly_report(
    session: AsyncSession,
    user: User,
    week_start: datetime,
    custom_format: str | None = None,
    custom_analysis: str | None = None,
) -> WeeklyUsageReport:
    """Generate and send weekly usage report to a user.

    Args:
        session: Database session
        user: User object
        week_start: Monday of the week
        custom_format: Optional custom formatting instructions
        custom_analysis: Optional custom AI analysis prompts

    Returns:
        Created WeeklyUsageReport instance
    """
    # Generate report data
    report_data = await generate_weekly_report_data(session, str(user.id), week_start)

    # Format report
    report_content = await format_weekly_report(
        report_data, week_start, custom_format, custom_analysis
    )

    # Send via Telegram
    bot_manager = get_bot_manager()
    await bot_manager.send_message(
        chat_id=user.telegram_id,
        text=report_content,
        parse_mode="Markdown",
    )

    # Track sent report
    weekly_report = WeeklyUsageReport(
        user_id=user.id,
        week_start=week_start,
        report_content=report_content,
    )
    session.add(weekly_report)
    await session.commit()
    await session.refresh(weekly_report)

    logger.info(
        "Sent weekly report to user %s (telegram_id=%s) for week starting %s",
        user.id,
        user.telegram_id,
        week_start.date(),
    )

    return weekly_report


async def get_report_for_week(
    session: AsyncSession, user_id: str, week_start: datetime
) -> WeeklyUsageReport | None:
    """Check if a report has already been sent for a specific week.

    Args:
        session: Database session
        user_id: User UUID
        week_start: Monday of the week

    Returns:
        WeeklyUsageReport if found, None otherwise
    """
    result = await session.execute(
        select(WeeklyUsageReport).where(
            and_(
                WeeklyUsageReport.user_id == user_id,
                WeeklyUsageReport.week_start == week_start,
            )
        )
    )
    return result.scalar_one_or_none()


async def get_current_week_start() -> datetime:
    """Get the Monday of the current week in the configured timezone.

    Returns:
        Monday of the current week as timezone-aware datetime
    """
    tz = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh (UTC+7)
    now = datetime.now(tz)

    # Find Monday of the current week
    days_since_monday = now.weekday()  # Monday = 0
    current_monday = now - timedelta(days=days_since_monday)
    return current_monday.replace(hour=0, minute=0, second=0, microsecond=0)