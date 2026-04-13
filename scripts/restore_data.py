#!/usr/bin/env python3
"""
Insert extracted receipt data into the database.

This script reads the extracted_receipts.json file and inserts the data into
the PostgreSQL database using SQLAlchemy models.

Usage:
    python restore_data.py [--dry-run]

Options:
    --dry-run    Preview what would be inserted without making changes
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.database import async_session_maker
from app.models.receipt import Receipt, ReceiptItem
from app.models.conversation import Conversation, ConversationMessage
from app.models.user import User


async def insert_data(extracted_data: dict, dry_run: bool = False):
    """Insert extracted data into database."""
    user_id = extracted_data.get("user_id")
    receipts = extracted_data.get("receipts", [])

    print(f"User ID: {user_id}")
    print(f"Receipts to insert: {len(receipts)}")

    if dry_run:
        print("\n=== DRY RUN MODE - No changes will be made ===\n")
        for receipt in receipts:
            print("Would insert receipt:")
            print(f"  - Merchant: {receipt.get('merchant_name')}")
            print(f"  - Total: {receipt.get('total')} {receipt.get('currency')}")
            print(f"  - Category: {receipt.get('category')}")
            print(f"  - Items: {len(receipt.get('items', []))}")
            print()
        return

    async with async_session_maker() as session:
        async with session.begin():
            # Check if user exists, create if not
            from sqlalchemy import select

            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()

            if not user:
                print(f"Creating user with ID: {user_id}")
                # You'll need to provide telegram_id
                print("ERROR: User does not exist. Please create the user first.")
                print(
                    f"Suggested SQL: INSERT INTO users (id, telegram_id, first_name) VALUES ('{user_id}', YOUR_TELEGRAM_ID, 'Recovered User');"
                )
                return

            inserted_count = 0
            for receipt_data in receipts:
                # Create conversation for this receipt
                conversation = Conversation(
                    user_id=user_id,
                    is_active=False,
                )
                session.add(conversation)
                await session.flush()  # Get conversation ID

                # Store conversation.started_at for potential use as receipt_datetime fallback
                conversation_started_at = conversation.started_at

                # Add conversation message
                message = ConversationMessage(
                    conversation_id=conversation.id,
                    role="assistant",
                    content=receipt_data.get("raw_response", "")[:1000],
                )
                session.add(message)

                # Parse datetime - use conversation.started_at as fallback
                receipt_datetime = None
                if receipt_data.get("receipt_datetime"):
                    try:
                        receipt_datetime = datetime.fromisoformat(
                            receipt_data["receipt_datetime"].replace("Z", "+00:00")
                        )
                    except (ValueError, TypeError):
                        pass

                # Use conversation.started_at as fallback if receipt_datetime is None
                if receipt_datetime is None:
                    receipt_datetime = conversation_started_at
                    print(f"  ℹ Using conversation.started_at as receipt_datetime: {receipt_datetime.isoformat()}")

                # Create receipt
                receipt = Receipt(
                    id=receipt_data.get("id"),
                    user_id=user_id,
                    conversation_id=conversation.id,
                    merchant_name=receipt_data.get("merchant_name") or "Unknown",
                    merchant_address=receipt_data.get("merchant_address"),
                    receipt_datetime=receipt_datetime,
                    category=receipt_data.get("category", "other"),
                    total=receipt_data.get("total") or 0,
                    currency=receipt_data.get("currency", "VND"),
                    subtotal=receipt_data.get("subtotal"),
                    tax_amount=receipt_data.get("tax_amount"),
                    discount=receipt_data.get("discount"),
                    notes=receipt_data.get("notes"),
                )
                session.add(receipt)
                await session.flush()  # Get receipt ID

                # Create receipt items
                for item_data in receipt_data.get("items", []):
                    item = ReceiptItem(
                        id=item_data.get("id"),
                        receipt_id=receipt.id,
                        name=item_data.get("name", "Unknown Item"),
                        quantity=item_data.get("quantity", 1),
                        unit_price=item_data.get("unit_price"),
                        amount=item_data.get("amount", 0),
                        confidence=item_data.get("confidence", "medium"),
                    )
                    session.add(item)

                inserted_count += 1
                print(
                    f"Inserted: {receipt.merchant_name} - {receipt.total} {receipt.currency}"
                )

            print(f"\n=== Inserted {inserted_count} receipts ===")


async def main():
    parser = argparse.ArgumentParser(description="Restore receipt data to database")
    parser.add_argument(
        "--dry-run", action="store_true", help="Preview without inserting"
    )
    parser.add_argument(
        "--file",
        type=str,
        default="data/recovery/extracted_receipts.json",
        help="Path to extracted receipts JSON file",
    )
    args = parser.parse_args()

    # Read extracted data
    file_path = Path(__file__).parent.parent / args.file
    if not file_path.exists():
        print(f"Error: File not found: {file_path}")
        sys.exit(1)

    with open(file_path, "r", encoding="utf-8") as f:
        extracted_data = json.load(f)

    print("Receipt Data Restoration")
    print("=" * 50)
    print(f"Source file: {file_path}")
    print(f"Extraction date: {extracted_data.get('extraction_date')}")
    print()

    await insert_data(extracted_data, dry_run=args.dry_run)


if __name__ == "__main__":
    asyncio.run(main())
