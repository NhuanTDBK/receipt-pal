"""Receipt Pal CLI PoC — Interactive receipt parsing with Gemini Flash."""

import os
import sys
import json
import base64
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
from openai import OpenAI

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    print("Error: GEMINI_API_KEY not set. Create a .env file or export it.")
    sys.exit(1)

MODEL = os.environ.get("MODEL", "gemini-2.0-flash")
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = PROJECT_ROOT / "data" / "receipts"
SYSTEM_PROMPT_PATH = PROJECT_ROOT / "docs" / "system_prompt.md"

client = OpenAI(
    api_key=GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

# ---------------------------------------------------------------------------
# Tool definitions (OpenAI function-calling format)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "AskUser",
            "description": "Ask one clarification question. For missing/uncertain fields and edit navigation.",
            "parameters": {
                "type": "object",
                "required": ["question", "options"],
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Short conversational question.",
                    },
                    "options": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "2-4 button labels. Include skip for skippable questions.",
                    },
                    "allow_skip": {
                        "type": "boolean",
                        "description": "false only for total and date.",
                    },
                    "field": {
                        "type": "string",
                        "enum": [
                            "total",
                            "date",
                            "merchant",
                            "category",
                            "line_item",
                            "edit_selection",
                        ],
                        "description": "Which field this resolves.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "SubmitReceipt",
            "description": (
                "Emit structured receipt data. "
                "mode=draft: send full receipt fields, shows card to user. "
                'mode=final: send ONLY {"mode": "final"} — CLI saves the stored draft, no data needed.'
            ),
            "parameters": {
                "type": "object",
                "required": ["mode"],
                "properties": {
                    "mode": {"type": "string", "enum": ["draft", "final"]},
                    "merchant": {
                        "type": "object",
                        "required": ["name"],
                        "properties": {
                            "name": {"type": "string"},
                            "address": {"type": "string"},
                        },
                    },
                    "datetime": {
                        "type": "string",
                        "description": "ISO 8601. Include time if visible.",
                    },
                    "billing_period": {
                        "type": "string",
                        "description": "YYYY-MM. Only for utility/service bills.",
                    },
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["name", "amount"],
                            "properties": {
                                "name": {"type": "string"},
                                "name_raw": {"type": "string"},
                                "quantity": {"type": "integer", "default": 1},
                                "unit_price": {"type": "integer"},
                                "amount": {"type": "integer"},
                                "confidence": {
                                    "type": "string",
                                    "enum": ["high", "medium", "low"],
                                },
                                "toppings": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "required": ["name"],
                                        "properties": {
                                            "name": {"type": "string"},
                                            "price": {"type": "integer"},
                                        },
                                    },
                                },
                                "modifiers": {
                                    "type": "object",
                                    "properties": {
                                        "sugar_level": {"type": "string"},
                                        "ice_level": {"type": "string"},
                                        "size": {"type": "string"},
                                    },
                                },
                                "food_tags": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "enum": [
                                            "sugary",
                                            "fried",
                                            "healthy",
                                            "alcohol",
                                            "caffeine",
                                            "dairy",
                                            "spicy",
                                            "non_food",
                                        ],
                                    },
                                },
                            },
                        },
                    },
                    "subtotal": {"type": "integer"},
                    "discount": {"type": "integer"},
                    "tax_rate": {"type": "number"},
                    "tax_amount": {"type": "integer"},
                    "total": {"type": "integer"},
                    "currency": {"type": "string", "default": "VND"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "dining",
                            "cafe",
                            "grocery",
                            "convenience",
                            "health",
                            "entertainment",
                            "transport",
                            "utilities",
                            "rent",
                            "other",
                        ],
                    },
                    "source": {
                        "type": "string",
                        "enum": [
                            "paper",
                            "shopeefood",
                            "grabfood",
                            "gofood",
                            "baemin",
                            "app_unknown",
                        ],
                        "default": "paper",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "UpdateReceipt",
            "description": (
                "Patch the current draft receipt. Send ONLY the fields that changed. "
                "Items are matched by their [id] shown in the receipt card — only include items that need updating."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "merchant": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "address": {"type": "string"},
                        },
                    },
                    "datetime": {"type": "string"},
                    "category": {
                        "type": "string",
                        "enum": [
                            "dining",
                            "cafe",
                            "grocery",
                            "convenience",
                            "health",
                            "entertainment",
                            "transport",
                            "utilities",
                            "rent",
                            "other",
                        ],
                    },
                    "currency": {"type": "string"},
                    "subtotal": {"type": "integer"},
                    "discount": {"type": "integer"},
                    "tax_rate": {"type": "number"},
                    "tax_amount": {"type": "integer"},
                    "total": {"type": "integer"},
                    "notes": {"type": "string"},
                    "items": {
                        "type": "array",
                        "description": "Only changed items. Each must include 'id' matching the [id] on the card.",
                        "items": {
                            "type": "object",
                            "required": ["id"],
                            "properties": {
                                "id": {
                                    "type": "integer",
                                    "description": "Incremental ID, start from 1",
                                },
                                "name": {"type": "string"},
                                "quantity": {"type": "integer"},
                                "unit_price": {"type": "integer"},
                                "amount": {"type": "integer"},
                                "toppings": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "price": {"type": "integer"},
                                        },
                                    },
                                },
                                "modifiers": {
                                    "type": "object",
                                    "properties": {
                                        "sugar_level": {"type": "string"},
                                        "ice_level": {"type": "string"},
                                        "size": {"type": "string"},
                                    },
                                },
                                "food_tags": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        },
    },
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def format_vnd(amount: int) -> str:
    """Format an integer as Vietnamese dong: 55000 -> 55.000d"""
    return f"{amount:,}d".replace(",", ".")


def format_currency(amount: int, currency: str = "VND") -> str:
    if currency == "VND":
        return format_vnd(amount)
    return f"{amount:,} {currency}"


def encode_image(image_path: str) -> dict:
    """Encode a local image as a base64 data URL for the vision API."""
    path = Path(image_path).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(f"Image not found: {path}")

    mime_map = {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
    }
    mime_type = mime_map.get(path.suffix.lower(), "image/jpeg")

    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{b64}"},
    }


def load_system_prompt() -> str:
    """Load the system prompt and append CLI-specific instructions."""
    text = SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    cli_note = (
        "\n\n---\n\n"
        "NOTE: The user is interacting via a terminal CLI, not Telegram. "
        "There are no inline keyboard buttons.\n\n"
        "HOW TOOLS WORK IN CLI:\n"
        "- AskUser: CLI displays your question and numbered options, then waits. "
        "The user's answer arrives as their NEXT user message — not in the tool result.\n"
        "- SubmitReceipt(draft): Send the full parsed receipt. CLI assigns [id] to each "
        "item and shows the card. User replies 'confirm', 'edit', or describes changes.\n"
        "- UpdateReceipt: Send ONLY changed fields. For items, include only changed items "
        "with their [id] from the card. CLI re-displays the updated card.\n"
        '- SubmitReceipt(final): Send ONLY {"mode": "final"} — no receipt data needed. '
        "CLI saves the stored draft automatically.\n\n"
        "EDIT FLOW: SubmitReceipt(draft) → user says what to change → "
        "UpdateReceipt(patch) → repeat until user confirms → SubmitReceipt(final).\n\n"
        "IMPORTANT: Only call ONE tool per response. Do not chain tools in a single turn."
    )
    return text + cli_note


# ---------------------------------------------------------------------------
# Receipt card display
# ---------------------------------------------------------------------------


def display_receipt_card(receipt: dict, mode: str):
    """Print a formatted receipt card to the terminal."""
    merchant = receipt.get("merchant", {})
    merchant_name = merchant.get("name", "Unknown")
    merchant_addr = merchant.get("address", "")
    dt = receipt.get("datetime", "")
    category = receipt.get("category", "")
    currency = receipt.get("currency", "VND")
    total = receipt.get("total", 0)

    label = "[DRAFT]" if mode == "draft" else "[SAVED]"

    print()
    print(f"  ┌─── {label} {'─' * (40 - len(label))}┐")
    print(f"  │ 🧾 {merchant_name}")
    if merchant_addr:
        print(f"  │    {merchant_addr}")
    print(f"  │ 📅 {dt}  •  {category}")
    print(f"  │{'─' * 45}│")

    for item in receipt.get("items", []):
        item_id = item.get("id", "")
        name = item.get("name", "???")
        qty = item.get("quantity", 1)
        amount = item.get("amount", 0)
        qty_str = f"{qty}x " if qty > 1 else ""
        id_str = f"[{item_id}] " if item_id != "" else ""
        amount_str = format_currency(amount, currency)
        line = f"{id_str}{qty_str}{name}"
        print(f"  │ {line:<32} {amount_str:>10} │")

        for topping in item.get("toppings", []):
            tp_name = topping.get("name", "")
            tp_price = topping.get("price", 0)
            price_str = (
                f"+{format_currency(tp_price, currency)}" if tp_price else "free"
            )
            print(f"  │   + {tp_name:<28} {price_str:>10} │")

        modifiers = item.get("modifiers", {})
        if modifiers:
            mod_parts = []
            if modifiers.get("sugar_level"):
                mod_parts.append(f"sugar: {modifiers['sugar_level']}")
            if modifiers.get("ice_level"):
                mod_parts.append(f"ice: {modifiers['ice_level']}")
            if modifiers.get("size"):
                mod_parts.append(f"size: {modifiers['size']}")
            if mod_parts:
                print(f"  │   ({', '.join(mod_parts)})")

        tags = item.get("food_tags", [])
        if tags:
            print(f"  │   [{', '.join(tags)}]")

    print(f"  │{'─' * 45}│")

    if receipt.get("discount"):
        disc = format_currency(receipt["discount"], currency)
        print(f"  │ {'Discount':<32} {'-' + disc:>10} │")
    if receipt.get("tax_amount"):
        tax = format_currency(receipt["tax_amount"], currency)
        print(f"  │ {'Tax':<32} {tax:>10} │")

    total_str = format_currency(total, currency)
    print(f"  │ {'TOTAL':<32} {total_str:>10} │")
    print(f"  └{'─' * 45}┘")
    print()


# ---------------------------------------------------------------------------
# Tool call handlers
# ---------------------------------------------------------------------------


def handle_ask_user(args: dict) -> str:
    """Display a question with numbered options. User answers in the next outer loop turn."""
    question = args.get("question", "")
    options = args.get("options", [])
    allow_skip = args.get("allow_skip", True)

    print(f"\n  Bot: {question}")
    for i, opt in enumerate(options, 1):
        print(f"    [{i}] {opt}")
    if allow_skip and not any("skip" in o.lower() for o in options):
        print(f"    [0] Skip")

    return "Question shown. User will answer next."


def handle_submit_receipt(
    args: dict, current_receipt: dict | None
) -> tuple[str, dict | None]:
    """Display receipt card and optionally save to file.

    Returns (tool_result_string, updated_current_receipt).
    draft: assigns sequential IDs to items, stores as current_receipt.
    final: saves current_receipt from CLI state (args data not needed).
    """
    mode = args.get("mode", "draft")

    if mode == "draft":
        # Assign sequential IDs so UpdateReceipt can patch by id
        receipt = dict(args)
        for i, item in enumerate(receipt.get("items", []), start=1):
            item["id"] = i
        display_receipt_card(receipt, "draft")
        print("  Type 'confirm' to save, 'edit' to modify, or describe changes.")
        return "Receipt card shown to user. Waiting for user response.", receipt

    elif mode == "final":
        if current_receipt is None:
            return (
                "Error: no draft receipt to save. Call SubmitReceipt(draft) first.",
                None,
            )
        filepath = save_receipt(current_receipt)
        display_receipt_card(current_receipt, "final")
        print(f"  ✅ Saved → {filepath}")
        return f"Receipt saved to {filepath}", None

    return "Unknown mode.", current_receipt


def handle_update_receipt(
    patch: dict, current_receipt: dict | None
) -> tuple[str, dict | None]:
    """Merge patch into current_receipt and re-display the card.

    Top-level scalar fields are overwritten. 'merchant' is shallow-merged.
    'items' are patched by id — only provided sub-fields are updated.
    Returns (tool_result_string, updated_current_receipt).
    """
    if current_receipt is None:
        return (
            "Error: no draft receipt to update. Call SubmitReceipt(draft) first.",
            None,
        )

    updated = dict(current_receipt)

    for key, value in patch.items():
        if key == "merchant":
            updated["merchant"] = {**updated.get("merchant", {}), **value}
        elif key == "items":
            items = [dict(item) for item in updated.get("items", [])]
            for item_patch in value:
                patch_id = item_patch.get("id")
                for item in items:
                    if item.get("id") == patch_id:
                        item.update({k: v for k, v in item_patch.items() if k != "id"})
                        break
            updated["items"] = items
        else:
            updated[key] = value

    display_receipt_card(updated, "draft")
    print("  Receipt updated. Type 'confirm' to save, or describe more changes.")
    return "Receipt updated and shown to user.", updated


def save_receipt(receipt: dict) -> Path:
    """Save a finalized receipt as a JSON file."""
    RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    merchant_name = receipt.get("merchant", {}).get("name", "unknown")
    slug = "".join(c if c.isalnum() else "_" for c in merchant_name)[:30]
    filename = f"{timestamp}_{slug}.json"

    filepath = RECEIPTS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(receipt, f, ensure_ascii=False, indent=2)

    return filepath


# ---------------------------------------------------------------------------
# Chat loop
# ---------------------------------------------------------------------------


def chat_loop():
    system_prompt = load_system_prompt()
    messages: list[dict] = [{"role": "system", "content": system_prompt}]
    current_receipt: dict | None = None  # stores the active draft with item IDs

    print()
    print("  ╔═══════════════════════════════════════════╗")
    print("  ║          Receipt Pal CLI (PoC)            ║")
    print("  ╠═══════════════════════════════════════════╣")
    print("  ║  Send a receipt image path to parse it.   ║")
    print("  ║  Or type a message to chat.               ║")
    print("  ║  Type 'quit' to exit.                     ║")
    print("  ╚═══════════════════════════════════════════╝")
    print()

    while True:
        try:
            user_input = input("  You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Goodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit", "q"):
            print("  Goodbye!")
            break

        # Check if input is an image path
        potential_path = Path(user_input.strip("'\"")).expanduser()
        if (
            potential_path.exists()
            and potential_path.suffix.lower() in IMAGE_EXTENSIONS
        ):
            try:
                image_content = encode_image(str(potential_path))
                content = [
                    {
                        "type": "text",
                        "text": "Here is a receipt photo. Please parse it.",
                    },
                    image_content,
                ]
            except FileNotFoundError as e:
                print(f"  Error: {e}")
                continue
        else:
            content = user_input

        messages.append({"role": "user", "content": content})

        # Single API call — tool results stay in history, user answers next turn
        full_content = ""
        tool_calls_by_idx: dict[int, dict] = {}
        printed_prefix = False
        tool_indicator_shown = False

        print("  ⏳ ...", end="", flush=True)

        try:
            stream = client.chat.completions.create(
                model=MODEL,
                messages=messages,
                tools=TOOLS,
                tool_choice="auto",
                stream=True,
            )

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta

                # Stream text content token by token
                if delta.content:
                    if not printed_prefix:
                        print(f"\r  Bot: ", end="", flush=True)
                        printed_prefix = True
                    print(delta.content, end="", flush=True)
                    full_content += delta.content

                # Accumulate tool call chunks using raw dict to capture
                # extra_content.google.thought_signature (Gemini thinking models)
                raw_chunk = chunk.model_dump()
                raw_tool_calls = (
                    raw_chunk.get("choices", [{}])[0].get("delta", {}).get("tool_calls")
                    or []
                )
                for tc_raw in raw_tool_calls:
                    idx = tc_raw.get("index", 0)
                    if idx not in tool_calls_by_idx:
                        tool_calls_by_idx[idx] = {
                            "id": "",
                            "type": "function",
                            "function": {"name": "", "arguments": ""},
                        }
                    if tc_raw.get("id"):
                        tool_calls_by_idx[idx]["id"] = tc_raw["id"]
                    fn = tc_raw.get("function") or {}
                    if fn.get("name"):
                        tool_calls_by_idx[idx]["function"]["name"] += fn["name"]
                        if not tool_indicator_shown and not printed_prefix:
                            name = tool_calls_by_idx[idx]["function"]["name"]
                            print(f"\r  🔧 {name}...", end="", flush=True)
                            tool_indicator_shown = True
                    if fn.get("arguments"):
                        tool_calls_by_idx[idx]["function"]["arguments"] += fn[
                            "arguments"
                        ]
                    # Preserve thought_signature so Gemini doesn't reject the next turn
                    extra = tc_raw.get("extra_content")
                    if extra:
                        tool_calls_by_idx[idx]["extra_content"] = extra

        except KeyboardInterrupt:
            print("\n  Goodbye!")
            return
        except Exception as e:
            print(f"\n  API Error: {e}")
            continue

        print(flush=True)

        tool_calls = [tool_calls_by_idx[i] for i in sorted(tool_calls_by_idx.keys())]

        # Append assembled assistant message to history
        assistant_msg: dict = {"role": "assistant", "content": full_content}
        if tool_calls:
            assistant_msg["tool_calls"] = tool_calls
        messages.append(assistant_msg)

        # Process tool calls and append results — user answers on next outer loop turn
        for tc in tool_calls:
            fn_name = tc["function"]["name"]
            raw_args = tc["function"]["arguments"]
            try:
                fn_args = (
                    json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                )
            except json.JSONDecodeError:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc["id"],
                        "content": "Error: could not parse tool arguments",
                    }
                )
                continue

            if fn_name == "AskUser":
                result = handle_ask_user(fn_args)
            elif fn_name == "SubmitReceipt":
                result, current_receipt = handle_submit_receipt(
                    fn_args, current_receipt
                )
            elif fn_name == "UpdateReceipt":
                result, current_receipt = handle_update_receipt(
                    fn_args, current_receipt
                )
            else:
                result = f"Unknown tool: {fn_name}"

            messages.append(
                {"role": "tool", "tool_call_id": tc["id"], "content": result}
            )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    chat_loop()
