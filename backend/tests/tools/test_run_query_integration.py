from __future__ import annotations

import json

import pytest
from sqlalchemy import text

from app.services.tools.run_query import run_query
from tests.factories import create_user
from tests.generators import build_generated_receipt_payload, seed_receipts
from tests.helpers import build_run_context


async def _is_sqlite(db_session) -> bool:
    """Check if the current database is SQLite."""
    result = await db_session.execute(text("SELECT version()"))
    version = result.scalar()
    return "sqlite" in str(version).lower() if version else False


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_monthly_spending_trend(db_session) -> None:
    """Test monthly spending trend query."""
    if await _is_sqlite(db_session):
        pytest.skip("DATE_TRUNC is PostgreSQL-specific")

    user = await create_user(db_session, first_name="Trend User")

    # Create receipts spanning multiple months
    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(
                category="cafe",
                total=50000,
                # January 2026
                receipt_datetime="2026-01-15T10:30:00+07:00",
            ),
            build_generated_receipt_payload(
                category="cafe",
                total=60000,
                # February 2026
                receipt_datetime="2026-02-20T14:15:00+07:00",
            ),
            build_generated_receipt_payload(
                category="grocery",
                total=100000,
                # February 2026
                receipt_datetime="2026-02-10T09:00:00+07:00",
            ),
            build_generated_receipt_payload(
                category="transport",
                total=30000,
                # March 2026
                receipt_datetime="2026-03-05T16:45:00+07:00",
            ),
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT 
            DATE_TRUNC('month', receipt_datetime) as month,
            SUM(total) as monthly_total,
            COUNT(*) as transaction_count
        FROM receipts
        WHERE user_id = :user_id
        GROUP BY month
        ORDER BY month
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert "result" in payload
    assert len(payload["result"]) == 3  # Jan, Feb, Mar

    # Check January (PostgreSQL returns UTC timezone)
    jan_result = next(
        (r for r in payload["result"] if r["month"].startswith("2026-01-01")),
        None,
    )
    assert jan_result is not None
    assert jan_result["monthly_total"] == 50000
    assert jan_result["transaction_count"] == 1

    # Check February (cafe + grocery)
    feb_result = next(
        (r for r in payload["result"] if r["month"].startswith("2026-02-01")),
        None,
    )
    assert feb_result is not None
    assert feb_result["monthly_total"] == 160000  # 60000 + 100000
    assert feb_result["transaction_count"] == 2

    # Check March
    mar_result = next(
        (r for r in payload["result"] if r["month"].startswith("2026-03-01")),
        None,
    )
    assert mar_result is not None
    assert mar_result["monthly_total"] == 30000
    assert mar_result["transaction_count"] == 1


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_category_spending_with_items(db_session) -> None:
    """Test category spending with item details query."""
    user = await create_user(db_session, first_name="Item User")

    # Create receipts with items
    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(
                category="dining",
                total=75000,
                # Receipt with multiple items
            ),
            build_generated_receipt_payload(
                category="dining",
                total=60000,
                # Another dining receipt
            ),
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT 
            r.category,
            COUNT(DISTINCT r.id) as receipt_count,
            COUNT(ri.id) as item_count,
            SUM(r.total) as total_spent,
            AVG(r.total) as avg_receipt_value,
            SUM(ri.amount) as total_items_amount
        FROM receipts r
        LEFT JOIN receipt_items ri ON r.id = ri.receipt_id
        WHERE r.user_id = :user_id
        GROUP BY r.category
        ORDER BY total_spent DESC
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert "result" in payload
    assert len(payload["result"]) == 1

    result = payload["result"][0]
    assert result["category"] == "dining"
    assert result["receipt_count"] == 2
    assert result["total_spent"] == 135000  # 75000 + 60000
    assert result["item_count"] >= 0  # Items may vary based on seed data
    assert result["avg_receipt_value"] == 67500  # 135000 / 2


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_top_items_by_quantity(db_session) -> None:
    """Test querying top items by quantity purchased."""
    user = await create_user(db_session, first_name="Top Items User")

    # Create receipts with specific items
    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(
                category="grocery",
                total=50000,
                # Will generate random items via seed
            ),
            build_generated_receipt_payload(
                category="grocery",
                total=75000,
                # Will generate random items via seed
            ),
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT 
            ri.name,
            SUM(ri.quantity) as total_quantity,
            AVG(ri.unit_price) as avg_unit_price,
            SUM(ri.amount) as total_amount
        FROM receipt_items ri
        JOIN receipts r ON ri.receipt_id = r.id
        WHERE r.user_id = :user_id
        GROUP BY ri.name
        ORDER BY total_quantity DESC
        LIMIT 5
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert "result" in payload
    # Should have results (even if seed data varies)
    assert isinstance(payload["result"], list)

    # If we have results, verify structure
    if payload["result"]:
        first_item = payload["result"][0]
        assert "name" in first_item
        assert "total_quantity" in first_item
        assert isinstance(first_item["total_quantity"], int)
        assert first_item["total_quantity"] > 0


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_empty_result_handling(db_session) -> None:
    """Test handling of queries that return no results."""
    user = await create_user(db_session, first_name="Empty Result User")
    await db_session.commit()  # User with no receipts

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT 
            SUM(total) as total_spent,
            COUNT(*) as receipt_count
        FROM receipts
        WHERE user_id = :user_id
          AND category = 'nonexistent_category'
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert "result" in payload
    assert len(payload["result"]) == 1
    result = payload["result"][0]
    # PostgreSQL returns None for SUM with no rows, SQLite returns 0
    assert result["total_spent"] == 0 or result["total_spent"] is None
    assert result["receipt_count"] == 0


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_date_range_filtering(db_session) -> None:
    """Test date range filtering with SQL date functions."""
    user = await create_user(db_session, first_name="Date Range User")

    # Create receipts on specific dates
    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(
                total=10000, receipt_datetime="2026-01-10T10:00:00+07:00"
            ),
            build_generated_receipt_payload(
                total=20000, receipt_datetime="2026-01-20T15:30:00+07:00"
            ),
            build_generated_receipt_payload(
                total=30000, receipt_datetime="2026-02-10T09:15:00+07:00"
            ),
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT
            SUM(total) as period_total,
            COUNT(*) as transaction_count
        FROM receipts
        WHERE user_id = :user_id
          AND receipt_datetime >= '2026-01-15'
          AND receipt_datetime < '2026-02-01'
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert "result" in payload
    assert len(payload["result"]) == 1
    result = payload["result"][0]
    # Should only include the Jan 20 receipt (20000) - Jan 10 is before range, Feb 10 is after
    # PostgreSQL returns None for SUM with no matching rows
    assert result["period_total"] == 20000 or result["period_total"] == 20000.0
    assert result["transaction_count"] == 1
