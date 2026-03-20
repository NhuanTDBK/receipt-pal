"""Context for the Receipt Pal parser agent."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy.orm import Session, sessionmaker


@dataclass
class ReceiptParserContext:
    """Carries mutable parsing state across tool calls within one session."""

    draft: dict | None = None
    item_counter: int = field(default=0)
    user_id: Optional[uuid.UUID] = None
    session_factory: Optional[sessionmaker[Session]] = None
    settings: Optional[object] = None  # UserSettings ORM instance
