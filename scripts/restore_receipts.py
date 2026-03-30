#!/usr/bin/env python3
"""
Final receipt recovery script - Database Insertion

This script inserts the partially recovered receipt data into the database.
IMPORTANT: The backup had truncated responses (200 char limit), so line items
are NOT available. Only merchant names, some totals, and dates were recovered.

Usage:
    python restore_receipts.py [--dry-run]
"""

import argparse
import asyncio
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session_maker
from app.models.receipt import Receipt, ReceiptItem
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User


USER_ID = uuid.UUID("4bfe5aac-1801-411d-9dec-f2f9fb8d583f")


async def ensure_user_exists(session: AsyncSession, telegram_id: int = 123456789):
    """Ensure the user exists in the database."""
    result = await session.execute(select(User).where(User.id == USER_ID))
    user = result.scalar_one_or_none()

    if not user:
        print(f"Creating user {USER_ID}...")
        user = User(
            id=USER_ID,
            telegram_id=telegram_id,
            first_name="Recovered User",
            username="recovered_user",
        )
        session.add(user)
        await session.flush()
        print("✓ User created")
    else:
        print(f"✓ User already exists: {user.first_name}")

    return user


async def insert_receipts(receipts_data: list, dry_run: bool = False):
    """Insert recovered receipts into database."""

    print(f"\n{'=' * 60}")
    print("RECEIPT RECOVERY - DATABASE INSERTION")
    print(f"{'=' * 60}")
    print(f"Total receipts to insert: {len(receipts_data)}")
    print(f"Mode: {'DRY RUN (no changes)' if dry_run else 'LIVE INSERTION'}")
    print()

    if dry_run:
        print("Would insert the following receipts:")
        for r in receipts_data:
            merchant = r.get("merchant_name") or "Unknown"
            total = r.get("total") or "N/A"
            date = r.get("receipt_datetime") or "N/A"
            items_count = len(r.get("items", []))
            print(f"  - {merchant}: {total}đ on {date} ({items_count} items)")
        return

    async with async_session_maker() as session:
        async with session.begin():
            # Ensure user exists
            await ensure_user_exists(session)

            inserted = 0
            skipped = 0

            for receipt_data in receipts_data:
                # Skip receipts without merchant name and total
                merchant = receipt_data.get("merchant_name")
                total = receipt_data.get("total")

                if not merchant and not total:
                    print("⚠ Skipping: No merchant or total")
                    skipped += 1
                    continue

                # Create conversation
                conversation = Conversation(
                    user_id=USER_ID,
                    is_active=False,
                )
                session.add(conversation)
                await session.flush()

                # Add conversation message with raw response
                raw_response = receipt_data.get("raw_response", "")
                message = ConversationMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=raw_response[:1000]
                    if raw_response
                    else "Receipt recovered from backup",
                )
                session.add(message)

                # Parse datetime
                receipt_datetime = None
                if receipt_data.get("receipt_datetime"):
                    try:
                        receipt_datetime = datetime.fromisoformat(
                            receipt_data["receipt_datetime"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                # Create receipt
                receipt = Receipt(
                    id=uuid.UUID(receipt_data["id"])
                    if "id" in receipt_data
                    else uuid.uuid4(),
                    user_id=USER_ID,
                    conversation_id=conversation.id,
                    merchant_name=merchant or "Unknown Merchant",
                    merchant_address=receipt_data.get("merchant_address"),
                    receipt_datetime=receipt_datetime,
                    category=receipt_data.get("category", "other"),
                    total=total or 0,
                    currency=receipt_data.get("currency", "VND"),
                    notes=f"Recovered from backup. Turn ID: {receipt_data.get('turn_id', 'unknown')}",
                )
                session.add(receipt)
                await session.flush()

                # Add items if any (unlikely due to backup truncation)
                for item_data in receipt_data.get("items", []):
                    item = ReceiptItem(
                        id=uuid.uuid4(),
                        receipt_id=receipt.id,
                        name=item_data.get("name", "Unknown Item"),
                        quantity=item_data.get("quantity", 1),
                        unit_price=item_data.get("unit_price"),
                        amount=item_data.get("amount", 0),
                        confidence=item_data.get("confidence", "low"),
                    )
                    session.add(item)

                inserted += 1
                print(
                    f"✓ Inserted: {receipt.merchant_name} - {receipt.total} {receipt.currency}"
                )

            print(f"\n{'=' * 60}")
            print("SUMMARY")
            print(f"{'=' * 60}")
            print(f"Inserted: {inserted} receipts")
            print(f"Skipped: {skipped} receipts")


async def main():
    parser = argparse.ArgumentParser(description="Restore receipts to database")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="data/recovery/all_extracted_receipts.json",
        help="Path to extracted receipts JSON file",
    )
    args = parser.parse_args()

    # Read extracted data
    file_path = Path(__file__).parent.parent / args.file
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    receipts = data.get("receipts", [])

    print("Receipt Recovery Tool")
    print(f"Source: {file_path}")
    print(f"Extraction date: {data.get('extraction_date')}")
    print(f"User ID: {data.get('user_id')}")

    await insert_receipts(receipts, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
