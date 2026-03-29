from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation
from app.models.receipt import Receipt, ReceiptItem
from app.models.user import User

DEFAULT_RECEIPT_DATETIME = datetime(2026, 3, 21, 10, 0, tzinfo=timezone.utc)


def _merge_dict(base: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, dict) and isinstance(value, dict):
            merged[key] = _merge_dict(current, value)
        else:
            merged[key] = value
    return merged


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def build_user(**overrides: Any) -> User:
    nonce = uuid.uuid4().hex[:8]
    base = {
        "id": uuid.uuid4(),
        "telegram_id": 100000 + int(uuid.uuid4().int % 900000),
        "username": f"tester_{nonce}",
        "first_name": "Tester",
    }
    return User(**_merge_dict(base, overrides))


def build_conversation(user_id: uuid.UUID, **overrides: Any) -> Conversation:
    base = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "is_active": True,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
    }
    return Conversation(**_merge_dict(base, overrides))


def build_receipt_payload(
    *,
    items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    payload = {
        "merchant": {"name": "Phê La", "address": "Thành Thái"},
        "datetime": DEFAULT_RECEIPT_DATETIME.isoformat(),
        "items": items
        or [
            {
                "name": "Trà sữa oolong",
                "name_raw": "Tra sua oolong",
                "quantity": 1,
                "amount": 60000,
                "confidence": "high",
                "food_tags": ["sugary", "caffeine"],
                "modifiers": {"sugar_level": "vừa", "ice_level": "vừa"},
            }
        ],
        "total": 60000,
        "currency": "VND",
        "category": "cafe",
        "source": "paper",
    }
    return _merge_dict(payload, overrides)


async def create_user(session: AsyncSession, **overrides: Any) -> User:
    user = build_user(**overrides)
    session.add(user)
    await session.flush()
    return user


async def create_conversation(
    session: AsyncSession,
    *,
    user: User | None = None,
    **overrides: Any,
) -> Conversation:
    user = user or await create_user(session)
    conversation = build_conversation(user_id=user.id, **overrides)
    session.add(conversation)
    await session.flush()
    return conversation


async def create_receipt(
    session: AsyncSession,
    *,
    user: User | None = None,
    conversation: Conversation | None = None,
    items: list[dict[str, Any]] | None = None,
    **overrides: Any,
) -> Receipt:
    user = user or await create_user(session)
    conversation = conversation or await create_conversation(session, user=user)
    payload = build_receipt_payload(items=items, **overrides)

    receipt = Receipt(
        id=uuid.uuid4(),
        user_id=user.id,
        conversation_id=conversation.id if conversation else None,
        merchant_name=payload["merchant"]["name"],
        merchant_address=payload["merchant"].get("address"),
        receipt_datetime=_parse_datetime(payload["datetime"]),
        billing_period=payload.get("billing_period"),
        category=payload.get("category", "other"),
        source=payload.get("source", "paper"),
        subtotal=payload.get("subtotal"),
        discount=payload.get("discount"),
        tax_rate=payload.get("tax_rate"),
        tax_amount=payload.get("tax_amount"),
        total=payload.get("total", 0),
        currency=payload.get("currency", "VND"),
        notes=payload.get("notes"),
        items=[
            ReceiptItem(
                id=uuid.uuid4(),
                name=item["name"],
                name_raw=item.get("name_raw"),
                quantity=item.get("quantity", 1),
                unit_price=item.get("unit_price"),
                amount=item["amount"],
                confidence=item.get("confidence", "high"),
                toppings=item.get("toppings"),
                modifiers=item.get("modifiers"),
                food_tags=item.get("food_tags"),
            )
            for item in payload.get("items", [])
        ],
    )
    session.add(receipt)
    await session.flush()
    return receipt
