from __future__ import annotations

import importlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from tests.factories import create_user
from tests.generators import build_generated_receipt_payload, seed_receipts
from tests.helpers import build_run_context

search_module = importlib.import_module("app.services.tools.search_receipts")


class FrozenDateTime(datetime):
    @classmethod
    def now(cls, tz=None):
        current = cls(2026, 3, 28, 12, 0, tzinfo=timezone.utc)
        if tz is None:
            return current.replace(tzinfo=None)
        return current.astimezone(tz)


def test_parse_relative_bound_uses_current_time_for_last_n_days(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "datetime", FrozenDateTime)

    lower_bound = search_module._parse_relative_bound("last 7 days", is_end=False)
    upper_bound = search_module._parse_relative_bound("today", is_end=True)

    assert lower_bound == FrozenDateTime.now(timezone.utc) - timedelta(days=7)
    assert upper_bound.date().isoformat() == "2026-03-28"


@pytest.mark.asyncio
async def test_search_receipts_rejects_invalid_date_ranges_before_querying() -> None:
    fake_session = AsyncMock()
    fake_session.execute = AsyncMock(
        side_effect=AssertionError("search should fail before querying the DB")
    )

    ctx = build_run_context(db_session=fake_session, user_id=uuid.uuid4())
    response = await search_module.search_receipts.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "query": "coffee",
                "start_date": "2026-03-30",
                "end_date": "2026-03-01",
            }
        ),
    )
    payload = json.loads(response)

    assert payload["error"] == "Invalid date filter: start_date must be <= end_date."


@pytest.mark.asyncio
@pytest.mark.database
async def test_search_receipts_finds_merchant_and_item_matches_for_current_user_only(
    db_session,
) -> None:
    user = await create_user(db_session, first_name="Search User")
    other_user = await create_user(db_session, first_name="Other Search User")

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
                category="grocery",
                merchant_name="WinMart+",
                items=[
                    {
                        "name": "Rau cải",
                        "amount": 18000,
                        "quantity": 1,
                        "unit_price": 18000,
                        "food_tags": ["healthy"],
                    }
                ],
                total=18000,
                index=1,
            ),
        ],
    )
    await seed_receipts(
        db_session,
        user=other_user,
        payloads=[
            build_generated_receipt_payload(
                category="cafe",
                merchant_name="Phê La",
                total=999999,
                index=1,
            )
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)

    merchant_response = await search_module.search_receipts.on_invoke_tool(
        ctx,
        json.dumps({"query": "Phê La"}),
    )
    merchant_payload = json.loads(merchant_response)
    assert merchant_payload["found"] == 1
    assert merchant_payload["receipts"][0]["merchant"] == "Phê La"
    assert merchant_payload["receipts"][0]["total"] == 60000

    item_response = await search_module.search_receipts.on_invoke_tool(
        ctx,
        json.dumps({"query": "Rau cải"}),
    )
    item_payload = json.loads(item_response)
    assert item_payload["found"] == 1
    assert item_payload["receipts"][0]["merchant"] == "WinMart+"
    assert item_payload["receipts"][0]["items"][0]["name"] == "Rau cải"


@pytest.mark.asyncio
@pytest.mark.database
async def test_search_receipts_respects_category_relative_and_iso_filters(
    db_session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(search_module, "datetime", FrozenDateTime)

    user = await create_user(db_session, first_name="Filter User")
    await seed_receipts(
        db_session,
        user=user,
        payloads=[
            build_generated_receipt_payload(
                category="cafe",
                merchant_name="Recent Cafe",
                datetime="2026-03-27T10:00:00+00:00",
                total=70000,
            ),
            build_generated_receipt_payload(
                category="cafe",
                merchant_name="Old Cafe",
                datetime="2026-03-05T09:00:00+00:00",
                total=50000,
                index=1,
            ),
            build_generated_receipt_payload(
                category="grocery",
                merchant_name="Recent Grocery",
                datetime="2026-03-26T18:00:00+00:00",
                total=90000,
            ),
        ],
    )
    await db_session.commit()

    ctx = build_run_context(db_session=db_session, user_id=user.id)

    relative_response = await search_module.search_receipts.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "query": "",
                "category": "cafe",
                "start_date": "last 7 days",
                "end_date": "today",
            }
        ),
    )
    relative_payload = json.loads(relative_response)
    assert relative_payload["found"] == 1
    assert relative_payload["receipts"][0]["merchant"] == "Recent Cafe"

    iso_response = await search_module.search_receipts.on_invoke_tool(
        ctx,
        json.dumps(
            {
                "query": "",
                "category": "cafe",
                "start_date": "2026-03-01",
                "end_date": "2026-03-10",
            }
        ),
    )
    iso_payload = json.loads(iso_response)
    assert iso_payload["found"] == 1
    assert iso_payload["receipts"][0]["merchant"] == "Old Cafe"

    empty_response = await search_module.search_receipts.on_invoke_tool(
        ctx,
        json.dumps({"query": "Nonexistent Merchant"}),
    )
    empty_payload = json.loads(empty_response)
    assert empty_payload == {
        "found": 0,
        "receipts": [],
        "note": "No receipts matched the search.",
    }
