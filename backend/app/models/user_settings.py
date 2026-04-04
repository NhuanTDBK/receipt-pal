import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class UserSettings(Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False, default="vi")
    response_preference: Mapped[str] = mapped_column(
        String(20), nullable=False, default="concise"
    )
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    weekly_report_enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    weekly_report_custom_format: Mapped[str | None] = mapped_column(Text, nullable=True)
    weekly_report_custom_analysis: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
