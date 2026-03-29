from __future__ import annotations

import pytest

from tests.generators import (
    build_generated_receipt_payload,
    generate_receipt_payloads,
    list_sample_receipt_fixtures,
    load_sample_receipt_fixture,
    seed_receipts,
)


def test_sample_receipt_fixtures_are_discoverable() -> None:
    fixtures = list_sample_receipt_fixtures()

    assert len(fixtures) >= 5
    assert all(path.suffix == ".json" for path in fixtures)


def test_load_sample_receipt_fixture_normalizes_payload_shape() -> None:
    payload = load_sample_receipt_fixture("20260321_002132_Phê_La.json")

    assert "mode" not in payload
    assert payload["merchant"]["name"] == "Phê La"
    assert payload["category"] == "cafe"
    assert "id" not in payload["items"][0]
    assert payload["subtotal"] == payload["total"]


def test_generate_receipt_payloads_cycles_categories_deterministically() -> None:
    payloads = generate_receipt_payloads(
        5,
        categories=["cafe", "dining", "utilities"],
    )

    assert [payload["category"] for payload in payloads] == [
        "cafe",
        "dining",
        "utilities",
        "cafe",
        "dining",
    ]
    assert payloads[2]["billing_period"] is not None


def test_build_generated_receipt_payload_supports_category_specific_defaults() -> None:
    payload = build_generated_receipt_payload(
        category="transport",
        merchant_name="GrabBike Test",
    )

    assert payload["merchant"]["name"] == "GrabBike Test"
    assert payload["category"] == "transport"
    assert payload["source"] == "app_unknown"
    assert payload["total"] == payload["subtotal"]


@pytest.mark.asyncio
@pytest.mark.database
async def test_seed_receipts_persists_generated_payloads(db_session) -> None:
    payloads = generate_receipt_payloads(3, categories=["cafe", "grocery"])

    receipts = await seed_receipts(db_session, payloads=payloads)
    await db_session.commit()

    assert len(receipts) == 3
    assert receipts[0].merchant_name
    assert receipts[1].category in {"cafe", "grocery"}
