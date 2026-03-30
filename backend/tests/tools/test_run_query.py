from __future__ import annotations

import json
import uuid

import pytest

from app.services.tools.run_query import run_query
from tests.factories import create_user
from tests.generators import build_generated_receipt_payload, seed_receipts
from tests.helpers import build_run_context


@pytest.mark.asyncio
async def test_run_query_rejects_write_operations_before_db_access() -> None:
    """Test that write operations are rejected before any DB access."""
    ctx = build_run_context(db_session=None, user_id=uuid.uuid4())
    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": "INSERT INTO receipts (total) VALUES (1000);"}),
    )
    payload = json.loads(response)

    assert "Only SELECT statements are allowed" in payload["error"]


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_returns_category_totals_for_current_user_only(
    db_session,
) -> None:
    user = await create_user(db_session, first_name="Analytics User")
    other_user = await create_user(db_session, first_name="Other User")

    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(category="cafe", total=60000),
            build_generated_receipt_payload(category="grocery", total=120000),
            build_generated_receipt_payload(category="cafe", total=50000, index=1),
        ],
    )
    await seed_receipts(
        db_session,
        user=other_user,
        payloads=[build_generated_receipt_payload(category="cafe", total=999999)],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT 
            category, 
            SUM(total) as total 
        FROM receipts 
        WHERE user_id = :user_id 
        GROUP BY category 
        ORDER BY total DESC
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert payload["result"] == [
        {"category": "grocery", "total": 120000},
        {"category": "cafe", "total": 110000},
    ]
    assert all(item["total"] != 999999 for item in payload["result"])


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_supports_top_merchant_style_analytics(db_session) -> None:
    user = await create_user(db_session, first_name="Merchant User")

    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(
                category="cafe",
                merchant_name="Phê La",
                total=60000,
            ),
            build_generated_receipt_payload(
                category="cafe",
                merchant_name="Phê La",
                total=65000,
                index=1,
            ),
            build_generated_receipt_payload(
                category="dining",
                merchant_name="Phở Phú Vương",
                total=85000,
            ),
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)
    sql_query = """
        SELECT 
            merchant_name, 
            COUNT(*) as visit_count,
            SUM(total) as total_spend
        FROM receipts
        WHERE user_id = :user_id
        GROUP BY merchant_name
        ORDER BY visit_count DESC, total_spend DESC
    """

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": sql_query}),
    )
    payload = json.loads(response)

    assert payload["result"][0] == {
        "merchant_name": "Phê La",
        "visit_count": 2,
        "total_spend": 125000,
    }


@pytest.mark.asyncio
@pytest.mark.database
async def test_run_query_validates_sql_security(db_session) -> None:
    user = await create_user(db_session, first_name="Security User")
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)

    # Test INSERT rejection
    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": "INSERT INTO receipts (total) VALUES (1000);"}),
    )
    payload = json.loads(response)
    assert "Only SELECT statements are allowed" in payload["error"]

    # Test DELETE rejection
    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": "DELETE FROM receipts WHERE user_id = :user_id;"}),
    )
    payload = json.loads(response)
    assert "Only SELECT statements are allowed" in payload["error"]

    # Test UNION injection attempt
    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "sql_query": "SELECT * FROM receipts WHERE user_id = :user_id UNION SELECT password FROM users;"
            }
        ),
    )
    payload = json.loads(response)
    assert "Potentially dangerous pattern: UNION" in payload["error"]

    # Test missing user_id (should still execute but might return all users' data - this is a business logic issue, not security)
    # Our validation doesn't require user_id, it's up to the agent to include it
    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"sql_query": "SELECT COUNT(*) as count FROM receipts;"}),
    )
    payload = json.loads(response)
    # This should succeed (validation passes) but return 0 since no receipts for this user
    assert "result" in payload
    assert payload["result"][0]["count"] == 0
