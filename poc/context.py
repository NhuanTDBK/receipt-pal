"""PoC run context — carries the implicit user_id and DB session factory.

The `user_id` is set at CLI startup from the POC_USER_ID env var and
injected into every tool via the OpenAI Agents SDK RunContextWrapper.
The model never sees it as a tool parameter.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session, sessionmaker


@dataclass
class ReceiptPalContext:
    """Dependency bag passed to every agent tool call."""

    user_id: uuid.UUID
    """Fixed PoC user — scopes all data-access tools implicitly."""

    session_factory: sessionmaker[Session]
    """Synchronous SQLAlchemy session factory for receipt analytics."""

    def get_session(self) -> Session:
        return self.session_factory()
