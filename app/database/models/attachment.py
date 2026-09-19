from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class AttachmentType(StrEnum):
    DOCUMENT = "document"
    PHOTO = "photo"


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    homework_id: Mapped[int] = mapped_column(
        ForeignKey("homeworks.id", ondelete="CASCADE"), index=True
    )
    telegram_file_id: Mapped[str] = mapped_column(String(512))
    file_type: Mapped[AttachmentType] = mapped_column(
        Enum(AttachmentType, native_enum=False),
        nullable=False,
    )
    file_name: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class HomeworkLink(Base):
    __tablename__ = "homework_links"

    id: Mapped[int] = mapped_column(primary_key=True)
    homework_id: Mapped[int] = mapped_column(
        ForeignKey("homeworks.id", ondelete="CASCADE"), index=True
    )
    url: Mapped[str] = mapped_column(String(2048))
    title: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
