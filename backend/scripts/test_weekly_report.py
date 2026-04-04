"""Test script to preview weekly usage report output.

This script displays a sample weekly usage report without requiring a database connection.
It uses mock data to show the report format and content.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure backend/ is on the Python path when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.weekly_usage_report import format_weekly_report


# Mock report data representing a typical week of spending
MOCK_REPORT_DATA = {
    "receipt_count": 7,
    "total_spent": 571000,
    "largest_expense": 125000,
    "largest_merchant": "Grab",
    "category_breakdown": [
        {"category": "cafe", "spent": 135000},
        {"category": "dining", "spent": 163000},
        {"category": "transport", "spent": 173000},
        {"category": "grocery", "spent": 100000},
    ],
    "top_merchants": [
        {"merchant": "Grab", "spent": 125000},
        {"merchant": "Phở Phú Vương", "spent": 85000},
        {"merchant": "Cơm Tấm Cali", "spent": 78000},
        {"merchant": "Bách Hóa Xanh", "spent": 100000},
        {"merchant": "Highlands Coffee", "spent": 75000},
    ],
    "top_items": [
        {"item": "Gấm", "count": 1},
        {"item": "Cơm tấm sườn", "count": 1},
        {"item": "Latte", "count": 1},
        {"item": "GrabCar", "count": 1},
        {"item": "Sữa tươi", "count": 1},
    ],
}


def print_sample_receipts() -> None:
    """Print the sample receipts that generated the report."""
    print("Sample receipts for this week:")
    print("-" * 80)
    receipts = [
        ("Monday", "Phê La", "cafe", 60000, "Gấm"),
        ("Monday", "Cơm Tấm Cali", "dining", 78000, "Cơm tấm sườn"),
        ("Tuesday", "Highlands Coffee", "cafe", 75000, "Latte"),
        ("Wednesday", "Grab", "transport", 125000, "GrabCar"),
        ("Thursday", "Bách Hóa Xanh", "grocery", 100000, "Sữa tươi, Táo Mỹ"),
        ("Friday", "Phở Phú Vương", "dining", 85000, "Phở bò tái"),
        ("Saturday", "Be", "transport", 48000, "BeBike"),
    ]

    for day, merchant, category, total, items in receipts:
        print(f"  {day:10s} | {merchant:20s} | {category:12s} | {total:>8,} VND | {items}")
    print()


def main() -> None:
    """Main function to display the weekly report."""
    print("=" * 80)
    print("WEEKLY USAGE REPORT PREVIEW")
    print("=" * 80)
    print()

    # Get current week's Monday
    tz = timezone(timedelta(hours=7))  # Asia/Ho_Chi_Minh (UTC+7)
    now = datetime.now(tz)
    days_since_monday = now.weekday()  # Monday = 0
    current_monday = now - timedelta(days=days_since_monday)
    week_start = current_monday.replace(hour=0, minute=0, second=0, microsecond=0)

    print(f"Week: {week_start.strftime('%b %d')} - {(week_start + timedelta(days=6)).strftime('%b %d, %Y')}")
    print()

    # Show sample receipts
    print_sample_receipts()

    # Show summary statistics
    print("Summary Statistics:")
    print("-" * 80)
    print(f"  Total receipts:     {MOCK_REPORT_DATA['receipt_count']}")
    print(f"  Total spent:        {MOCK_REPORT_DATA['total_spent']:,} VND")
    print(f"  Largest expense:    {MOCK_REPORT_DATA['largest_expense']:,} VND ({MOCK_REPORT_DATA['largest_merchant']})")
    print()

    # Show category breakdown
    print("Category Breakdown:")
    print("-" * 80)
    for cat in MOCK_REPORT_DATA["category_breakdown"]:
        percentage = (cat["spent"] / MOCK_REPORT_DATA["total_spent"]) * 100
        print(f"  {cat['category'].title():12s} | {cat['spent']:>10,} VND | {percentage:>5.1f}%")
    print()

    # Generate and display the formatted report
    print("=" * 80)
    print("FORMATTED WEEKLY REPORT (as sent via Telegram)")
    print("=" * 80)
    print()

    # Mock the AI insights function to avoid actual LLM call
    import asyncio
    from unittest.mock import patch

    async def generate_report() -> str:
        with patch(
            "app.services.weekly_usage_report._generate_ai_insights",
            return_value="Your food and dining expenses are the highest this week, accounting for 28.5% of total spending. Consider meal prepping to reduce dining costs. Transport is also significant at 30.3% - consider using public transport or cycling for shorter trips.",
        ):
            report = await format_weekly_report(MOCK_REPORT_DATA, week_start)
        return report

    report = asyncio.run(generate_report())
    print(report)
    print()

    print("=" * 80)
    print("CUSTOM FORMAT EXAMPLE")
    print("=" * 80)
    print()

    # Show example with custom format
    custom_format = """📊 **Weekly Spending Summary**
{week_range}

💰 **Total:** {total_spent:,} VND
🛒 **Transactions:** {receipt_count}

**Top Categories:**
{category_breakdown}

{ai_insights}"""

    async def generate_custom_report() -> str:
        with patch(
            "app.services.weekly_usage_report._generate_ai_insights",
            return_value="Focus on reducing dining and transport expenses next week.",
        ):
            report = await format_weekly_report(
                MOCK_REPORT_DATA, week_start, custom_format=custom_format
            )
        return report

    custom_report = asyncio.run(generate_custom_report())
    print(custom_report)
    print()

    print("=" * 80)
    print("Test script completed!")
    print("=" * 80)


if __name__ == "__main__":
    main()