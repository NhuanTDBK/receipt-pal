# Changelog

All notable changes to Receipt Pal are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---


## [v2.1.6] — 2026-03-30

### Fixed
- **Receipt time ordering** — `list_receipts()` now orders by `receipt_datetime` instead of `created_at`, ensuring analytic queries and search use actual receipt purchase time as the default time column

---

## [v2.1.5] — 2026-03-30

### Changed
- **Test database requirement** — tests now require PostgreSQL via `TEST_DATABASE_URL` environment variable; SQLite fallback removed
- **Test fixtures** — `build_generated_receipt_payload` now supports `receipt_datetime` and `items` parameters for better test control

### Fixed
- **Decimal serialization** — `run_query` tool now properly serializes PostgreSQL `Decimal` values to JSON
- **Test assertions** — updated to handle PostgreSQL's UTC timezone format and `None` for empty `SUM()` results
- **Test database detection** — `_is_sqlite()` now works correctly with PostgreSQL

---

## [v2.1.4] — 2026-03-29

### Added
- **Comprehensive test suite** — backend now has a full test suite with unit, integration, and real-LLM tests
- **Testing documentation** — detailed guide for running different test types (fast default, PostgreSQL-backed, real-LLM verification)
- **Documentation index** — `docs/index.md` for better project navigation

### Fixed
- **Type checking in models** — added `TYPE_CHECKING` imports to resolve forward reference warnings in `conversation.py`, `receipt.py`, and `user.py`
- **Timezone handling** — replaced `datetime.UTC` with `timezone.utc` for Python 3.12 compatibility
- **ISO datetime parsing** — fixed parsing to properly handle 'Z' suffix in datetime strings
- **SQL injection vulnerability** — replaced Python code execution with parameterized SQL queries in `run_query` tool

### Changed
- **Analytics tool migration** — transitioned `run_query` from SQLAlchemy Python code execution to raw SQL with parameter binding
- **PoC agent structure** — refactored agent and CLI implementations for better modularity
- **Tool implementations** — improved error handling and cleaned up unused imports
- **Project documentation** — updated README with testing guide and WISHLIST.md with feature roadmap

---


## [v2.1.3] — 2026-03-27

### Changed
- **Analytics date-handling guidance** — updated `backend/app/prompts/analytics_instructions.md` to require multilingual time interpretation and normalization to concrete ISO `start_date`/`end_date` bounds before `search_receipts` calls.

### Fixed
- **Time-range analytics execution** — `run_query` sandbox now exposes `date`, `datetime`, and `timedelta`, enabling safe date-window queries (e.g., last week/this month) without blocked imports.
- **Receipt search date filtering** — `search_receipts` now supports `start_date` and `end_date` filters and validates invalid ranges.
- **Relative date support in search** — `search_receipts` now accepts relative English phrases (`today`, `last week`, `last N days`, etc.) as a fallback parser.
- **Duplicate post-parse message** — removed redundant follow-up chat text after tool-driven UI updates (draft card / inline keyboard) by suppressing `final_output` when tools already edited the status message.

---

## [v2.1.2] — 2026-03-21

### Fixed
- **Multimodal input format for OpenAI Agents SDK** — `_build_input()` was using Chat Completions content-part types (`text`, `image_url` with nested `{url}` dict) which the SDK's `Converter.items_to_messages()` does not recognise. Parts are now formatted using SDK-native types: `input_text` and `input_image` with a plain string `image_url`. The multimodal message is also wrapped in a list (`list[TResponseInputItem]`) instead of a bare dict, which previously caused the SDK to iterate over dict keys and raise `UserError: Unhandled item type or structure: role`.

---

## [v2.1.1] — 2026-03-21

### Fixed
- **Receipt/PDF photos failed to parse** — `_build_input()` was returning a flat list of content-part dicts (`{"type": "text", ...}`, `{"type": "image_url", ...}`) which the `openai-agents` SDK rejected with `UserError: Unhandled item type or structure`. Content parts are now wrapped in a valid `EasyInputMessageParam` (`{"role": "user", "content": [...]}`) before being passed to `Runner.run()`.

### Changed
- **Deploy script** (`infra/terraform/scripts/deploy-receipt-pal.sh`) — now runs `git fetch --tags origin main` before deploying and accepts an optional `TAG` argument to pin a specific release; defaults to the latest semver tag reachable from `main`.

---

## [v2.1.0] — 2026-03-20

### Added
- **Analytics tools** — users can now ask spending questions in natural language directly in Telegram chat:
  - `search_receipts` — keyword / category search across receipts and line items
  - `run_query` — open-ended analytics via LLM-generated SQLAlchemy queries executed in a sandboxed read-only namespace (`AsyncSession.run_sync()`)
  - `answer_faq` — product/feature questions answered from a static corpus
- **`docs/faq.md`** — shared FAQ corpus (24 entries) covering all production features: PDF support, text parsing, memory, settings, delivery platforms, analytics tools, bot commands, and more
- **`backend/app/prompts/analytics_instructions.md`** — analytics tool-selection rules and SQLAlchemy query patterns injected into agent system prompt

### Changed
- Agent renamed from `Receipt-Pal Parser` → `Receipt-Pal` to reflect combined parsing + analytics capability
- Agent tool list expanded from 6 → 9 tools (added `search_receipts`, `run_query`, `answer_faq`)
- POC `answer_faq` updated to reference shared `docs/faq.md`

---

## [v2.0.1] — 2026-03-20

### Fixed
- **Plain-text messages silently dropped** — added `StateFilter(None)` fallback handler that routes free-text messages (e.g. "change to Vietnamese") to the agent when no FSM state is active. Previously these produced `"Update is not handled"` warnings and were ignored.
- Router registration order corrected: callbacks and media handlers registered before commands so the fallback cannot shadow specific handlers.

---

## [v2.0.0] — 2026-03-20

### Added
- **OpenAI Agents SDK** — replaces raw OpenAI client; typed `@function_tool` implementations with Pydantic schemas eliminate ~200 lines of manual JSON tool definitions
- **`SQLAlchemySession`** for automatic conversation history persistence; removes manual `_build_gemini_history()` and `conversation_repo.load_history()` calls
- **Memory tool** (`set_memory`) — agent persists free-text user notes across sessions, stored in new `memories` table
- **Settings tool** (`update_settings`) — agent silently infers and persists language, response style, and location preferences
- **`UserSettings` model** — per-user language, response_preference, location; injected as static instructions header at session start
- **`/settings` command** — users can view their current preferences
- New DB models: `UserSettings`, `Memory`
- New repositories: `user_settings_repo`, `memory_repo`
- Alembic migration `b2c3d4e5f6a7`: adds `user_settings` and `memories` tables
- `TelegramAgentContext` dataclass for typed tool access to bot handles and session state
- `agent_runner.py` service orchestrating `Runner.run()` with session management and token tracking
- `OPENAI_AGENTS_DISABLE_TRACING=1` env var in Terraform to suppress SDK tracing noise

### Changed
- `ReceiptParser` replaced by typed `@function_tool` implementations (`ask_user`, `submit_receipt_draft/final`, `update_receipt`)
- Config: `gemini_api_key` → `openai_api_key`, `gemini_base_url` → `openai_base_url` (backward-compat aliases maintained)
- Photo and callback handlers simplified — delegate to `run_agent()` instead of managing `on_tool_call` closures
- `/start` command now ensures `UserSettings` row exists for new users
- System prompt extended with Memory and Settings sections

### Removed
- `receipt_parser.py` — 447 lines of manual streaming loop, JSON tool schemas, and tool dispatch

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
