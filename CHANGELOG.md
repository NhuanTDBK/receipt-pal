# Changelog

All notable changes to Receipt Pal are documented here.  
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [v1.1.1] — 2026-03-14

### Changed
- Rewrote `README.md` with a features overview, local development guide, and production deployment instructions

---

## [v1.1.0] — 2026-03-14

### Changed
- Enhanced system prompt loading in `receipt_parser.py` with improved handling logic
- Added comprehensive `docs/system_prompt.md` documenting the AI prompt structure

---

## [v1.0.3] — 2026-03-14

### Added
- **PDF receipt input** — users can now send PDF files directly to the bot; parsed using the same Gemini AI pipeline as photo receipts (no conversion step needed)
- New `document.py` handler with PDF MIME type filter, 20 MB size guard, and friendly rejection for unsupported file types
- `_encode_media()` in `receipt_parser.py` encodes both images (`image/jpeg`) and PDFs (`application/pdf`) as base64 data URLs for Gemini
- PDF parsing guidance added to `docs/system_prompt.md` (embedded text preference, multi-page support, utility bill `billing_period` extraction)

### Changed
- `_process_photos()` in `photo.py` renamed to `_process_receipt()` with `is_pdf` flag — shared core logic for both photo and PDF flows
- `ReceiptParser.parse()` gains optional `pdfs: list[bytes]` parameter (backward compatible)
- `/help` and welcome message updated to mention PDF support (max 20 MB)

### Story
- [v1.0.2 story spec](docs/stories/v1.0.2-pdf-receipt-input.md)

---

## [v1.0.2] — 2026-03-14

### Fixed
- Langfuse 4.x compatibility: replaced bare `session_id`/`user_id` kwargs in `chat.completions.create()` with `@observe` decorator + OpenTelemetry span attributes, resolving `TypeError` on startup

### Added
- `backend/scripts/test_langfuse_kwargs.py` smoke-test script to verify Langfuse tracing kwargs

---

## [v1.0.1] — 2026-03-03

### Added
- **Token tracking per conversation** — `input_tokens`, `output_tokens`, `total_tokens` columns on the `conversations` table (Alembic migration included)
- **Langfuse LLM observability** — all Gemini API calls traced with `session_id` (conversation) and `user_id` (Telegram user); optional, gracefully disabled when env vars are absent
- `/usage` command — shows total input/output/combined token counts across all user conversations
- `TokenUsage` dataclass returned from `ReceiptParser.parse()` for accumulation in the DB
- `add_token_usage()` and `get_usage_stats()` repository helpers on `conversation_repo`

### Changed
- `ReceiptParser.parse()` now returns `(messages, TokenUsage)` tuple instead of `messages` alone
- `LANGFUSE_SECRET_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_BASE_URL` documented in `.env.example`

### Story
- [v1.0.1 story spec](docs/stories/v1.0.1-token-tracking-langfuse.md)

---

## [v1.0.0] — 2026-03-03

### Added
- Initial release — Telegram bot powered by Gemini Flash vision AI
- Photo receipt parsing with Vietnamese OCR support (diacritics, VND formatting)
- Multi-photo (album) support — up to 1.5 s collection window
- Agentic tool-calling flow: `AskUser`, `SubmitReceipt` (draft/final), `UpdateReceipt`
- Inline keyboard confirm / edit / cancel flow with FSM state machine
- Receipt data model: merchant, datetime, line items, toppings, modifiers, food tags, totals, category, source
- Delivery app receipt support: ShopeeFood, GrabFood, GoFood, Baemin
- Utility bill support with `billing_period` extraction
- `/start`, `/help`, `/history`, `/stats` commands
- PostgreSQL persistence via SQLAlchemy async + Alembic migrations
- RocksDB photo cache (avoids redundant Telegram downloads)
- Redis FSM storage with MemoryStorage fallback
- Docker Compose deployment with Terraform VPS infra
