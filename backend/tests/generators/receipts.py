from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from tests.factories import (
    DEFAULT_RECEIPT_DATETIME,
    build_receipt_payload,
    create_conversation,
    create_receipt,
    create_user,
)

SAMPLE_RECEIPTS_DIR = Path(__file__).resolve().parents[3] / "data" / "receipts"

_CATEGORY_TEMPLATES: dict[str, list[dict[str, Any]]] = {
    "cafe": [
        {
            "merchant": {"name": "Phê La", "address": "Thành Thái"},
            "items": [
                {
                    "name": "Gấm",
                    "amount": 60000,
                    "quantity": 1,
                    "unit_price": 60000,
                    "food_tags": ["sugary", "caffeine"],
                    "modifiers": {"sugar_level": "vừa", "ice_level": "vừa"},
                }
            ],
        },
        {
            "merchant": {"name": "Highlands Coffee", "address": "Nguyễn Huệ"},
            "items": [
                {
                    "name": "Latte",
                    "amount": 75000,
                    "quantity": 1,
                    "unit_price": 75000,
                    "food_tags": ["caffeine", "dairy"],
                }
            ],
        },
    ],
    "dining": [
        {
            "merchant": {"name": "Cơm Tấm Cali", "address": "Quận 3"},
            "items": [
                {
                    "name": "Cơm tấm sườn",
                    "amount": 78000,
                    "quantity": 1,
                    "unit_price": 78000,
                    "food_tags": [],
                }
            ],
        },
        {
            "merchant": {"name": "Phở Phú Vương", "address": "Phú Nhuận"},
            "items": [
                {
                    "name": "Phở bò tái",
                    "amount": 85000,
                    "quantity": 1,
                    "unit_price": 85000,
                    "food_tags": ["healthy"],
                }
            ],
        },
    ],
    "grocery": [
        {
            "merchant": {"name": "Bách Hóa Xanh", "address": "Gò Vấp"},
            "items": [
                {
                    "name": "Sữa tươi",
                    "amount": 42000,
                    "quantity": 1,
                    "unit_price": 42000,
                    "food_tags": ["dairy"],
                },
                {
                    "name": "Táo Mỹ",
                    "amount": 58000,
                    "quantity": 1,
                    "unit_price": 58000,
                    "food_tags": ["healthy"],
                },
            ],
        },
        {
            "merchant": {"name": "WinMart+", "address": "Bình Thạnh"},
            "items": [
                {
                    "name": "Trứng gà",
                    "amount": 36000,
                    "quantity": 1,
                    "unit_price": 36000,
                    "food_tags": [],
                },
                {
                    "name": "Rau cải",
                    "amount": 18000,
                    "quantity": 1,
                    "unit_price": 18000,
                    "food_tags": ["healthy"],
                },
            ],
        },
    ],
    "transport": [
        {
            "merchant": {"name": "Grab", "address": "HCMC"},
            "items": [
                {
                    "name": "GrabCar",
                    "amount": 125000,
                    "quantity": 1,
                    "unit_price": 125000,
                    "food_tags": [],
                }
            ],
            "source": "app_unknown",
        },
        {
            "merchant": {"name": "Be", "address": "HCMC"},
            "items": [
                {
                    "name": "BeBike",
                    "amount": 48000,
                    "quantity": 1,
                    "unit_price": 48000,
                    "food_tags": [],
                }
            ],
            "source": "app_unknown",
        },
    ],
    "utilities": [
        {
            "merchant": {"name": "EVN", "address": "HCMC"},
            "items": [
                {
                    "name": "Tiền điện",
                    "amount": 450000,
                    "quantity": 1,
                    "unit_price": 450000,
                    "food_tags": ["non_food"],
                }
            ],
        },
        {
            "merchant": {"name": "SAWACO", "address": "HCMC"},
            "items": [
                {
                    "name": "Tiền nước",
                    "amount": 180000,
                    "quantity": 1,
                    "unit_price": 180000,
                    "food_tags": ["non_food"],
                }
            ],
        },
    ],
}


def list_sample_receipt_fixtures() -> list[Path]:
    return sorted(SAMPLE_RECEIPTS_DIR.glob("*.json"))


def normalize_receipt_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = copy.deepcopy(payload)
    normalized.pop("mode", None)
    normalized.setdefault("currency", "VND")
    normalized.setdefault("source", "paper")
    normalized.setdefault("category", "other")
    normalized.setdefault("merchant", {"name": "Unknown"})

    items = normalized.setdefault("items", [])
    for item in items:
        item.pop("id", None)
        item.setdefault("confidence", "high")
        item.setdefault("quantity", 1)
        item.setdefault("food_tags", [])
        item.setdefault("toppings", [])

    if normalized.get("subtotal") is None and normalized.get("total") is not None:
        normalized["subtotal"] = normalized["total"]

    return normalized


def load_sample_receipt_fixture(name: str) -> dict[str, Any]:
    fixture_path = SAMPLE_RECEIPTS_DIR / name
    if not fixture_path.exists():
        raise FileNotFoundError(f"No sample receipt fixture named {name!r}")

    with fixture_path.open("r", encoding="utf-8") as handle:
        payload = json.load(handle)
    return normalize_receipt_payload(payload)


def build_generated_receipt_payload(
    *,
    index: int = 0,
    category: str = "cafe",
    days_ago: int = 0,
    merchant_name: str | None = None,
    total: int | None = None,
    receipt_datetime: str | None = None,
    items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    if category not in _CATEGORY_TEMPLATES:
        raise ValueError(
            f"Unsupported category {category!r}. "
            f"Expected one of: {', '.join(sorted(_CATEGORY_TEMPLATES))}"
        )

    template = copy.deepcopy(
        _CATEGORY_TEMPLATES[category][index % len(_CATEGORY_TEMPLATES[category])]
    )
    merchant = template["merchant"]
    if merchant_name is not None:
        merchant["name"] = merchant_name

    # Use provided items or template items
    payload_items = items if items is not None else template["items"]
    computed_total = total or sum(item["amount"] for item in payload_items)
    # Use provided receipt_datetime or calculate from days_ago
    if receipt_datetime is not None:
        dt = datetime.fromisoformat(receipt_datetime.replace("Z", "+00:00"))
    else:
        dt = DEFAULT_RECEIPT_DATETIME - timedelta(days=days_ago + index)
    timestamp = dt.isoformat()
    # Remove items from overrides to avoid duplicate keyword argument
    overrides.pop("items", None)
    payload = build_receipt_payload(
        merchant=merchant,
        datetime=timestamp,
        items=payload_items,
        subtotal=computed_total,
        total=computed_total,
        category=category,
        source=template.get("source", "paper"),
        **overrides,
    )

    if category == "utilities":
        payload["billing_period"] = dt.strftime("%Y-%m")

    return normalize_receipt_payload(payload)


def generate_receipt_payloads(
    count: int,
    *,
    categories: Sequence[str] | None = None,
    start_days_ago: int = 0,
) -> list[dict[str, Any]]:
    categories = categories or tuple(_CATEGORY_TEMPLATES.keys())
    payloads: list[dict[str, Any]] = []

    for index in range(count):
        category = categories[index % len(categories)]
        payloads.append(
            build_generated_receipt_payload(
                index=index,
                category=category,
                days_ago=start_days_ago + index,
            )
        )

    return payloads


async def seed_receipts(
    session: AsyncSession,
    *,
    payloads: Sequence[dict[str, Any]],
    user=None,
    conversation=None,
):
    user = user or await create_user(session)
    conversation = conversation or await create_conversation(session, user=user)

    receipts = []
    for payload in payloads:
        normalized = normalize_receipt_payload(payload)
        receipt = await create_receipt(
            session,
            user=user,
            conversation=conversation,
            items=normalized.get("items"),
            **{key: value for key, value in normalized.items() if key != "items"},
        )
        receipts.append(receipt)

    await session.flush()
    return receipts
