#!/usr/bin/env python3
"""
Enhanced extraction script to find receipts with line items.
"""

import json
import re
import uuid
from pathlib import Path


def extract_receipts_with_items():
    backup_file = "/Users/nhuantran/Downloads/history backup_datasets_jkzJaZR63ZKOsQ-GtZj5Dw_2026-03-29T16_21_36.269Z.jsonl"

    with open(backup_file, "r", encoding="utf-8") as f:
        lines = f.readlines()

    receipts_with_items = []

    for line in lines:
        data = json.loads(line)
        turn_id = data.get("turnId", "")
        response = data.get("response", [])
        if not response:
            continue

        candidates = response[0].get("candidates", [])
        if not candidates:
            continue

        content = candidates[0].get("content", {})
        resp_parts = content.get("parts", [])
        resp_texts = [p.get("text", "") for p in resp_parts if "text" in p]
        resp_text = "\n".join(resp_texts)

        # Look for patterns that indicate itemized receipts
        # Pattern 1: Lines with **Item Name**: priceđ
        item_pattern1 = (
            r"\*\s*\*\*?([^*\n]+?)\*?\*?\s*[:\-]?\s*\(?([\d.,]+)\s*(?:đ|VNĐ)?\)?"
        )
        items1 = re.findall(item_pattern1, resp_text)

        # Pattern 2: Lines with - Item Name: price
        item_pattern2 = (
            r"^\s*[-–]\s*\*?([^*\n:]+?)\*?\s*[:\-]?\s*([\d.,]+)\s*(?:đ|d|VNĐ)?"
        )
        items2 = re.findall(item_pattern2, resp_text, re.MULTILINE)

        all_items = items1 + items2

        if all_items:
            # Extract merchant name
            merchant = None
            merchant_patterns = [
                r"từ\s+([^,.\n]+?)(?:\s+vào\s+ngày|\s+\(|\.|\n|$)",
                r"at\s+([^,.\n]+?)(?:\s+on\s+|\s+\(|\.|\n|$)",
                r"visited\s+([^,.\n]+?)(?:\s+\(|\s+on\s+|\.|\n|$)",
                r"của\s+([^,.\n]+?)(?:\s*:\s*|\.|\n|$)",
            ]
            for pattern in merchant_patterns:
                match = re.search(pattern, resp_text, re.IGNORECASE)
                if match:
                    merchant = match.group(1).strip()
                    merchant = re.sub(r'["\'\*]', "", merchant)
                    if len(merchant) > 2:
                        break

            # Extract date
            date = None
            date_match = re.search(r"(\d{1,2})[/-](\d{1,2})[/-](\d{4})", resp_text)
            if date_match:
                d, m, y = date_match.groups()
                date = f"{y}-{int(m):02d}-{int(d):02d}"

            # Extract total
            total = None
            total_match = re.search(r"[Tt]ổng.*?([\d.,]+)\s*(?:đ|d|VNĐ)", resp_text)
            if total_match:
                total = int(total_match.group(1).replace(".", "").replace(",", ""))

            # Clean up items
            clean_items = []
            for item in all_items:
                name = item[0].strip()
                price_str = item[1].replace(".", "").replace(",", "")
                try:
                    price = int(price_str)
                    if price > 1000 and len(name) > 2:
                        clean_items.append({"name": name, "price": price})
                except ValueError:
                    pass

            if clean_items:
                receipts_with_items.append(
                    {
                        "id": str(uuid.uuid4()),
                        "turn_id": turn_id,
                        "merchant": merchant,
                        "date": date,
                        "total": total,
                        "items": clean_items,
                        "raw_response": resp_text[:500],
                    }
                )

    return receipts_with_items


def main():
    receipts = extract_receipts_with_items()

    print(f"Found {len(receipts)} receipts with items\n")

    for r in receipts:
        print(f"=== {r['merchant'] or 'Unknown'} ===")
        print(f"Date: {r['date']}, Total: {r['total']}")
        print("Items:")
        for item in r["items"]:
            print(f"  - {item['name']}: {item['price']}đ")
        print()

    # Save to file
    output_file = Path(
        "/Users/nhuantran/Working/learn/receipt-pal/data/recovery/receipts_with_items.json"
    )
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(
            {"count": len(receipts), "receipts": receipts},
            f,
            indent=2,
            ensure_ascii=False,
        )

    print(f"Saved to: {output_file}")


if __name__ == "__main__":
    main()
