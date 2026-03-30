#!/usr/bin/env python3
"""
Comprehensive receipt extraction from Google AI Studio backup.
This script extracts ALL available receipt data, including summaries and itemized lists.
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any


def parse_backup_file(filepath: str) -> list[dict]:
    """Parse JSONL backup file."""
    conversations = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    conversations.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return conversations


def extract_user_message(turn: dict) -> str:
    """Extract user message text."""
    request = turn.get("request", {})
    contents = request.get("contents", [])
    if not contents:
        return ""
    parts = contents[0].get("parts", [])
    texts = [p.get("text", "") for p in parts if "text" in p]
    return " ".join(texts)


def extract_assistant_response(turn: dict) -> str:
    """Extract assistant response text."""
    response = turn.get("response", [])
    if not response:
        return ""
    candidates = response[0].get("candidates", [])
    if not candidates:
        return ""
    content = candidates[0].get("content", {})
    parts = content.get("parts", [])
    texts = [p.get("text", "") for p in parts if "text" in p]
    return "\n".join(texts)


def is_receipt_parsing_request(user_message: str) -> bool:
    """Check if user sent a receipt photo."""
    if not user_message:
        return False
    patterns = [
        r"here is a receipt photo",
        r"parse.*receipt",
        r"receipt.*photo",
        r"phân tích.*hóa đơn",
    ]
    message_lower = user_message.lower()
    return any(re.search(p, message_lower) for p in patterns)


def parse_receipt_from_response(
    response_text: str, turn_id: str, create_time: str
) -> dict[str, Any] | None:
    """Parse receipt data from LLM response."""
    if not response_text:
        return None

    text = response_text
    receipt = {
        "id": str(uuid.uuid4()),
        "turn_id": turn_id,
        "create_time": create_time,
        "merchant_name": None,
        "merchant_address": None,
        "receipt_datetime": None,
        "total": None,
        "currency": "VND",
        "category": "other",
        "items": [],
        "raw_response": text,
    }

    # Extract merchant name
    merchant_patterns = [
        r"from\s+([^,.\n\(]+?)(?:\s+at\s+|\s+on\s+|\s+\(|\.|\n|$)",
        r"at\s+([^,.\n\(]+?)(?:\s+on\s+|\s+\(|\.|\n|$)",
        r"nhận\s+(?:được\s+)?hóa\s+đơn\s+(?:từ\s+)?([^,.\n\(]+?)(?:\s+at\s+|\s+on\s+|\.|\n|$)",
        r"phân\s+tích\s+hóa\s+đơn\s+(?:từ\s+)?([^,.\n\(]+?)(?:\s+at\s+|\s+on\s+|\.|\n|$)",
        r"cập\s+nhật\s+(?:tên\s+)?quán\s+thành\s+([^,.\n]+?)(?:\.|\n|$)",
        r"ghi\s+nhận\s+hóa\s+đơn\s+(?:từ\s+)?([^,.\n\(]+?)(?:\.|\n|$)",
        r"nhận\s+được\s+hóa\s+đơn\s+(?:từ\s+)?\*\*([^*]+)\*\*",
        r"đã\s+lưu\s+hóa\s+đơn\s+(?:của\s+bạn\s+)?(?:từ\s+)?([^,.\n]+?)(?:\.|\n|$)",
        r"đơn\s+hàng\s+của\s+bạn\s+(?:tại\s+)?([^,.\n]+?)(?:\.|\n|$)",
        r"trích\s+xuất\s+thông\s+tin\s+từ\s+biên\s+nhận\s+của\s+([^,.\n]+?)(?:\s*:|\.|\n|$)",
    ]
    for pattern in merchant_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            merchant = match.group(1).strip()
            merchant = re.sub(r'["\'\*]', "", merchant)
            if len(merchant) > 2 and len(merchant) < 100:
                receipt["merchant_name"] = merchant
                break

    # Extract address
    address_patterns = [
        r"\(([^)]+(?:Cầu Giấy|Hà Nội|Hải Phòng|TP\.?HCM)[^)]*)\)",
    ]
    for pattern in address_patterns:
        match = re.search(pattern, text)
        if match:
            receipt["merchant_address"] = match.group(1).strip()
            break

    # Extract total amount
    total_patterns = [
        r"Tổng\s+tiền[:\s]+([\d.,]+)",
        r"Total[:\s]+([\d.,]+)",
        r"([\d.,]+)\s*(?:đ|VND|VNĐ)(?:\s|$|\.)",
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

    # Extract date
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

    # Extract items from bullet points
    item_patterns = [
        r"\*\s*\*\*?([^*\n]+?)\*?\*?\s*[:\-]?\s*\(?([\d.,]+)\s*(?:đ|VNĐ)?\)?",
        r"^\s*[-–]\s*\*?([^*\n:]+?)\*?\s*[:\-]?\s*([\d.,]+)\s*(?:đ|d|VNĐ)?",
    ]
    for pattern in item_patterns:
        matches = re.findall(pattern, text, re.MULTILINE)
        for match in matches:
            name = match[0].strip()
            price_str = match[1].replace(".", "").replace(",", "")
            try:
                price = int(price_str)
                # Filter out summary lines
                if (
                    price > 1000
                    and len(name) > 2
                    and not any(
                        x in name.lower()
                        for x in ["tổng", "total", "dining", "cafe", "grocery"]
                    )
                ):
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

    # Determine category
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
                "bánh tráng",
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
                "điện máy xanh",
            ],
            "shopping": ["electronics", "fashion", "store", "shop"],
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

    return (
        receipt
        if receipt["merchant_name"] or receipt["total"] or receipt["items"]
        else None
    )


def extract_summary_receipts(conversations: list[dict]) -> list[dict]:
    """Extract receipt mentions from summary/statistics responses."""
    summaries = []

    for turn in conversations:
        response_text = extract_assistant_response(turn)
        if not response_text:
            continue

        # Look for date/merchant/price patterns in summaries
        # Pattern: **15/03/2025** - Siêu thị WinMart: 1.250.000đ
        summary_pattern = r"\*\*?(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})\*\*?\s*[-–]\s*([^:]+?):\s*([\d.,]+)(?:đ)?"
        matches = re.findall(summary_pattern, response_text)

        for match in matches:
            date_str, merchant, price_str = match
            try:
                price = int(price_str.replace(".", "").replace(",", ""))
                # Parse date
                d, m, y = re.match(
                    r"(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})", date_str
                ).groups()
                if len(y) == 2:
                    y = "20" + y
                parsed_date = f"{y}-{int(m):02d}-{int(d):02d}T00:00:00+00:00"

                summaries.append(
                    {
                        "id": str(uuid.uuid4()),
                        "turn_id": turn.get("turnId", ""),
                        "merchant_name": merchant.strip(),
                        "receipt_datetime": parsed_date,
                        "total": price,
                        "currency": "VND",
                        "category": "other",
                        "items": [],
                        "source": "summary_extraction",
                        "raw_response": response_text[:200],
                    }
                )
            except (ValueError, AttributeError):
                pass

    return summaries


def main():
    backup_file = "/Users/nhuantran/Downloads/history backup_datasets_jkzJaZR63ZKOsQ-GtZj5Dw_2026-03-29T16_21_36.269Z.jsonl"
    output_dir = Path("/Users/nhuantran/Working/learn/receipt-pal/data/recovery")
    output_dir.mkdir(parents=True, exist_ok=True)

    print("Parsing backup file...")
    conversations = parse_backup_file(backup_file)
    print(f"Found {len(conversations)} conversation turns")

    # Extract receipts from receipt parsing responses
    receipts_from_parsing = []
    parsing_requests = 0

    for turn in conversations:
        user_msg = extract_user_message(turn)
        if is_receipt_parsing_request(user_msg):
            parsing_requests += 1
            response = extract_assistant_response(turn)
            receipt = parse_receipt_from_response(
                response, turn.get("turnId", ""), turn.get("createTime", "")
            )
            if receipt:
                receipts_from_parsing.append(receipt)

    # Extract receipts from summary responses
    receipts_from_summaries = extract_summary_receipts(conversations)

    # Combine all receipts
    all_receipts = receipts_from_parsing + receipts_from_summaries

    # Remove duplicates based on merchant + date + total
    seen = set()
    unique_receipts = []
    for r in all_receipts:
        key = (r.get("merchant_name"), r.get("receipt_datetime"), r.get("total"))
        if key not in seen:
            seen.add(key)
            unique_receipts.append(r)

    # Generate output
    output = {
        "user_id": "4bfe5aac-1801-411d-9dec-f2f9fb8d583f",
        "extraction_date": datetime.now().isoformat(),
        "statistics": {
            "total_conversation_turns": len(conversations),
            "receipt_parsing_requests": parsing_requests,
            "receipts_from_parsing": len(receipts_from_parsing),
            "receipts_from_summaries": len(receipts_from_summaries),
            "total_unique_receipts": len(unique_receipts),
        },
        "receipts": unique_receipts,
    }

    # Save to file
    output_file = output_dir / "all_extracted_receipts.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Print summary
    print(f"\n{'=' * 60}")
    print("EXTRACTION SUMMARY")
    print(f"{'=' * 60}")
    print(f"Total conversation turns: {len(conversations)}")
    print(f"Receipt parsing requests: {parsing_requests}")
    print(f"Receipts from parsing responses: {len(receipts_from_parsing)}")
    print(f"Receipts from summary responses: {len(receipts_from_summaries)}")
    print(f"Total unique receipts: {len(unique_receipts)}")
    print(f"\nSaved to: {output_file}")

    # Print merchant list
    print(f"\n{'=' * 60}")
    print("MERCHANTS FOUND")
    print(f"{'=' * 60}")
    merchants = {}
    for r in unique_receipts:
        m = r.get("merchant_name") or "Unknown"
        if m not in merchants:
            merchants[m] = {"count": 0, "total": 0}
        merchants[m]["count"] += 1
        if r.get("total"):
            merchants[m]["total"] += r["total"]

    for merchant, data in sorted(merchants.items()):
        total_str = f"{data['total']:,.0f}đ" if data["total"] > 0 else "N/A"
        print(f"  - {merchant}: {data['count']} receipt(s), Total: {total_str}")


if __name__ == "__main__":
    main()
