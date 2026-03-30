#!/usr/bin/env python3
"""
Extract receipt data from Google AI Studio backup JSONL file.

This script reads the conversation history backup and extracts structured receipt
data from LLM responses. It generates JSON files for review before database insertion.

Usage:
    python extract_receipts_from_backup.py

Output:
    - extracted_receipts.json: Structured receipt data
    - extraction_report.txt: Summary of extraction results
    - conversations.json: Conversation metadata
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_jsonl_file(filepath: str) -> list[dict]:
    """Parse JSONL file into list of conversation turns."""
    conversations = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    conversations.append(json.loads(line))
                except json.JSONDecodeError as e:
                    print(f"Warning: Could not parse line: {e}")
    return conversations


def extract_user_message(turn: dict) -> str | None:
    """Extract user message text from conversation turn."""
    request = turn.get("request", {})
    contents = request.get("contents", [])
    if not contents:
        return None

    parts = contents[0].get("parts", [])
    if not parts:
        return None

    # Get text parts, skip image data
    texts = []
    for part in parts:
        if "text" in part:
            texts.append(part["text"])

    return " ".join(texts) if texts else None


def extract_assistant_response(turn: dict) -> str | None:
    """Extract assistant response text from conversation turn."""
    response = turn.get("response", [])
    if not response:
        return None

    candidates = response[0].get("candidates", [])
    if not candidates:
        return None

    content = candidates[0].get("content", {})
    parts = content.get("parts", [])

    texts = []
    for part in parts:
        if "text" in part:
            texts.append(part["text"])

    return " ".join(texts) if texts else None


def is_receipt_parsing_request(user_message: str | None) -> bool:
    """Check if user message is a receipt parsing request."""
    if not user_message:
        return False
    patterns = [
        r"here is a receipt photo",
        r"parse.*receipt",
        r"receipt.*photo",
    ]
    message_lower = user_message.lower()
    return any(re.search(p, message_lower) for p in patterns)


def parse_receipt_from_response(
    response_text: str, turn_id: str
) -> dict[str, Any] | None:
    """
    Parse receipt data from LLM response text.
    Uses regex patterns to extract structured data.
    """
    if not response_text:
        return None

    receipt = {
        "id": str(uuid.uuid4()),
        "merchant_name": None,
        "merchant_address": None,
        "receipt_datetime": None,
        "total": None,
        "currency": "VND",
        "category": "other",
        "subtotal": None,
        "tax_amount": None,
        "discount": None,
        "notes": None,
        "items": [],
        "source_turn_id": turn_id,
        "raw_response": response_text,
    }

    text = response_text

    # Extract merchant name - look for patterns like "from [Merchant]", "at [Merchant]"
    merchant_patterns = [
        r"from\s+([^,.\n]+?)(?:\s+at\s+|\s+on\s+|\s+\(|\.|\n|$)",
        r"at\s+([^,.\n]+?)(?:\s+on\s+|\s+\(|\.|\n|$)",
        r"nhận\s+(?:được\s+)?hóa\s+đơn\s+(?:từ\s+)?([^,.\n]+?)(?:\s+at\s+|\s+on\s+|\.|\n|$)",
        r"phân\s+tích\s+hóa\s+đơn\s+(?:từ\s+)?([^,.\n]+?)(?:\s+at\s+|\s+on\s+|\.|\n|$)",
        r"cập\s+nhật\s+(?:tên\s+)?quán\s+thành\s+([^,.\n]+?)(?:\.|\n|$)",
        r"ghi\s+nhận\s+hóa\s+đơn\s+(?:từ\s+)?([^,.\n]+?)(?:\.|\n|$)",
        r"nhận\s+được\s+hóa\s+đơn\s+(?:từ\s+)?\*\*([^*]+)\*\*",
        r"đã\s+lưu\s+hóa\s+đơn\s+(?:của\s+bạn\s+)?(?:từ\s+)?([^,.\n]+?)(?:\.|\n|$)",
    ]
    for pattern in merchant_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            merchant = match.group(1).strip()
            # Clean up merchant name
            merchant = re.sub(r'["\'\*]', "", merchant)
            if len(merchant) > 2 and len(merchant) < 100:
                receipt["merchant_name"] = merchant
                break

    # Extract total amount - look for patterns like "1.250.000đ", "Total: 84,000"
    total_patterns = [
        r"Tổng\s+tiền[:\s]+([\d.,]+)\s*(đ|VND|VNĐ)?",
        r"Total[:\s]+([\d.,]+)",
        r"([\d.,]+)\s*(đ|VND|VNĐ)(?:\s|$|\.)",
        r"tổng\s+cộng[:\s]+([\d.,]+)",
        r"tổng\s+chi\s+tiêu\s+(?:là\s+)?([\d.,]+)",
    ]
    for pattern in total_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(".", "").replace(",", "")
            try:
                receipt["total"] = int(amount_str)
                break
            except ValueError:
                pass

    # Extract date - look for patterns like "15/03/2025", "March 15th"
    date_patterns = [
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})",
        r"(\d{1,2})[/-](\d{1,2})[/-](\d{2})",
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                day, month, year = match.groups()
                if len(year) == 2:
                    year = "20" + year
                receipt["receipt_datetime"] = (
                    f"{year}-{int(month):02d}-{int(day):02d}T00:00:00+00:00"
                )
                break
            except (ValueError, TypeError):
                pass

    # Extract items - look for bullet points or numbered lists with prices
    lines = text.split("\n")
    for line in lines:
        line = line.strip()
        # Skip empty lines and headers
        if not line or any(
            h in line.lower()
            for h in ["dining", "cafe", "grocery", "tổng", "total", "chi tiêu"]
        ):
            continue

        # Look for lines with bullet points and prices
        if any(c in line for c in ["*", "-", "•", "·"]) and (
            "đ" in line or re.search(r"\d{3,}", line)
        ):
            # Try to extract item name and price
            # Pattern: **Item Name**: 68.000đ or * Item Name: 68.000đ
            item_match = re.search(
                r"[\*\-•·\*]+\s*\*?([^\*\n]+?)\*?\s*[:\-]?\s*([\d.,]+)\s*(?:đ|VND)?",
                line,
            )
            if item_match:
                name = item_match.group(1).strip()
                price_str = item_match.group(2).replace(".", "").replace(",", "")
                try:
                    price = int(price_str)
                    if price > 1000 and len(name) > 2 and len(name) < 200:
                        receipt["items"].append(
                            {
                                "id": str(uuid.uuid4()),
                                "name": name,
                                "quantity": 1,
                                "unit_price": price,
                                "amount": price,
                                "confidence": "medium",
                            }
                        )
                except ValueError:
                    pass

    # Determine category based on merchant name
    if receipt["merchant_name"]:
        merchant_lower = receipt["merchant_name"].lower()
        category_keywords = {
            "dining": [
                "phở",
                "cơm",
                "quán",
                "nhà hàng",
                "restaurant",
                "food",
                "chicken",
                "bonchon",
                "lẩu",
                "nướng",
                "hải sản",
            ],
            "cafe": [
                "coffee",
                "cafe",
                "cà phê",
                "starbucks",
                "highland",
                "phê la",
                "trà",
                "tea",
            ],
            "grocery": [
                "siêu thị",
                "gs 25",
                "circle k",
                "winmart",
                "grocery",
                "mart",
                "co.op",
                "lotte",
            ],
            "shopping": ["điện máy", "electronics", "fashion", "store", "shop"],
            "transport": [
                "grab",
                "be",
                "gojek",
                "taxi",
                "xe",
                "shopeefood",
                "baemin",
                "now",
            ],
        }
        for category, keywords in category_keywords.items():
            if any(kw in merchant_lower for kw in keywords):
                receipt["category"] = category
                break

    # Only return if we found at least merchant name or total
    if receipt["merchant_name"] or receipt["total"]:
        return receipt
    return None


def extract_conversations(conversations: list[dict]) -> list[dict]:
    """Extract conversation metadata."""
    results = []
    for turn in conversations:
        turn_id = turn.get("turnId", "")
        create_time = turn.get("createTime", "")
        user_message = extract_user_message(turn)
        assistant_response = extract_assistant_response(turn)

        results.append(
            {
                "turn_id": turn_id,
                "create_time": create_time,
                "user_message": user_message,
                "assistant_response": assistant_response[:500] + "..."
                if assistant_response and len(assistant_response) > 500
                else assistant_response,
            }
        )
    return results


def main():
    # File paths
    backup_file = "/Users/nhuantran/Downloads/history backup_datasets_jkzJaZR63ZKOsQ-GtZj5Dw_2026-03-29T16_21_36.269Z.jsonl"
    output_dir = Path("/Users/nhuantran/Working/learn/receipt-pal/data/recovery")
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Reading backup file: {backup_file}")
    conversations = parse_jsonl_file(backup_file)
    print(f"Found {len(conversations)} conversation turns")

    # Extract receipts
    receipts = []
    parsing_requests = 0
    failed_extractions = []

    for turn in conversations:
        turn_id = turn.get("turnId", "")
        user_message = extract_user_message(turn)
        assistant_response = extract_assistant_response(turn)

        if is_receipt_parsing_request(user_message):
            parsing_requests += 1
            receipt = parse_receipt_from_response(assistant_response, turn_id)
            if receipt:
                receipts.append(receipt)
            else:
                failed_extractions.append(
                    {
                        "turn_id": turn_id,
                        "user_message": user_message,
                        "response_preview": assistant_response[:200]
                        if assistant_response
                        else None,
                    }
                )

    # Generate output files

    # 1. Extracted receipts JSON
    receipts_output = {
        "user_id": "4bfe5aac-1801-411d-9dec-f2f9fb8d583f",
        "extraction_date": datetime.now().isoformat(),
        "total_receipts": len(receipts),
        "receipts": receipts,
    }

    receipts_file = output_dir / "extracted_receipts.json"
    with open(receipts_file, "w", encoding="utf-8") as f:
        json.dump(receipts_output, f, indent=2, ensure_ascii=False)
    print(f"✓ Written: {receipts_file}")

    # 2. Extraction report
    report_lines = [
        "Receipt Data Extraction Report",
        "=" * 50,
        f"Backup file: {backup_file}",
        f"Extraction date: {datetime.now().isoformat()}",
        "",
        "Summary:",
        f"  - Total conversation turns: {len(conversations)}",
        f"  - Receipt parsing requests: {parsing_requests}",
        f"  - Successfully extracted: {len(receipts)}",
        f"  - Failed extractions: {len(failed_extractions)}",
        "",
        "Merchants found:",
    ]

    merchants = set()
    for receipt in receipts:
        if receipt.get("merchant_name"):
            merchants.add(receipt["merchant_name"])

    for merchant in sorted(merchants):
        count = sum(1 for r in receipts if r.get("merchant_name") == merchant)
        report_lines.append(f"  - {merchant}: {count} receipt(s)")

    if failed_extractions:
        report_lines.extend(
            [
                "",
                "Failed extractions:",
            ]
        )
        for fail in failed_extractions[:10]:  # Show first 10
            report_lines.append(f"  - Turn {fail['turn_id'][:20]}...")
            if fail["response_preview"]:
                preview = fail["response_preview"].replace("\n", " ")[:100]
                report_lines.append(f"    Response: {preview}...")

    report_file = output_dir / "extraction_report.txt"
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines))
    print(f"✓ Written: {report_file}")

    # 3. Conversations metadata
    conv_data = extract_conversations(conversations)
    conversations_file = output_dir / "conversations.json"
    with open(conversations_file, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total_conversations": len(conv_data),
                "conversations": conv_data,
            },
            f,
            indent=2,
            ensure_ascii=False,
        )
    print(f"✓ Written: {conversations_file}")

    print("\n" + "=" * 50)
    print("Extraction complete!")
    print(f"Review the files in: {output_dir}")
    print("\nNext steps:")
    print("1. Review extracted_receipts.json for data quality")
    print("2. Edit any incorrect entries manually if needed")
    print("3. Run restore script to insert into database")


if __name__ == "__main__":
    main()
