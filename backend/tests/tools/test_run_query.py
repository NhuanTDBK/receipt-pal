from __future__ import annotations

import importlib
import json
import uuid

import pytest

from app.repositories import receipt_repo
from app.services.tools.run_query import run_query
from tests.factories import create_user
from tests.generators import build_generated_receipt_payload, seed_receipts
from tests.helpers import build_run_context


@pytest.mark.asyncio
async def test_run_query_rejects_write_operations_before_db_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_query_module = importlib.import_module("app.services.tools.run_query")

    async def should_not_open_session():
        raise AssertionError(
            "run_query should reject write code before opening a DB session"
        )

    monkeypatch.setattr(
        run_query_module, "async_session_factory", should_not_open_session
    )

    ctx = build_run_context(db_session=None, user_id=uuid.uuid4())
    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"query_code": "session.add(Receipt())\nresult = []"}),
    )
    payload = json.loads(response)

    assert "Disallowed operation detected" in payload["error"]


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
    query_code = "\n".join(
        [
            "stmt = (",
            "    select(Receipt.category, func.sum(Receipt.total).label('total'))",
            "    .where(Receipt.user_id == user_id)",
            "    .group_by(Receipt.category)",
            "    .order_by(func.sum(Receipt.total).desc())",
            ")",
            "rows = session.execute(stmt).all()",
            "result = [{'category': row.category, 'total': row.total} for row in rows]",
        ]
    )

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"query_code": query_code}),
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
    query_code = "\n".join(
        [
            "stmt = (",
            "    select(",
            "        Receipt.merchant_name,",
            "        func.count(Receipt.id).label('visit_count'),",
            "        func.sum(Receipt.total).label('total_spend'),",
            "    )",
            "    .where(Receipt.user_id == user_id)",
            "    .group_by(Receipt.merchant_name)",
            "    .order_by(func.count(Receipt.id).desc(), func.sum(Receipt.total).desc())",
            ")",
            "rows = session.execute(stmt).all()",
            "result = [",
            "    {'merchant': row.merchant_name, 'visit_count': row.visit_count, 'total_spend': row.total_spend}",
            "    for row in rows",
            "]",
        ]
    )

    response = await run_query.on_invoke_tool(
        ctx,
        json.dumps({"query_code": query_code}),
    )
    payload = json.loads(response)

    assert payload["result"][0] == {
        "merchant": "Phê La",
        "visit_count": 2,
        "total_spend": 125000,
    }


@pytest.mark.asyncio
@pytest.mark.database
async def test_get_spending_stats_groups_categories_descending(db_session) -> None:
    user = await create_user(db_session, first_name="Stats User")

    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(category="cafe", total=70000),
            build_generated_receipt_payload(category="cafe", total=60000, index=1),
            build_generated_receipt_payload(category="grocery", total=90000),
        ],
    )
    await db_session.commit()

    stats = await receipt_repo.get_spending_stats(db_session, user.id)

    assert stats == [
        {"category": "cafe", "total": 130000},
        {"category": "grocery", "total": 90000},
    ]
