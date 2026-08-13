from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.models_base import Base


class NoticeFocus(Base):
    __tablename__ = "notice_focus"
    __table_args__ = (
        UniqueConstraint("user_id", "data_id", name="uq_notice_focus_user_data"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    data_id: Mapped[int] = mapped_column(
        ForeignKey("collected_data.id"),
        nullable=False,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
