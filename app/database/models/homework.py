from datetime import date

from sqlalchemy import (
    Date,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base, TimestampMixin


class Homework(TimestampMixin, Base):
    __tablename__ = "homeworks"
    __table_args__ = (
        Index("ix_homeworks_group_deadline", "group_id", "deadline"),
        UniqueConstraint(
            "group_id", "subject_id", "deadline",
            name="uq_homework_group_subject_deadline",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    subject_id: Mapped[int] = mapped_column(
        ForeignKey("subjects.id", ondelete="CASCADE"), index=True
    )
    author_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(4000))
    deadline: Mapped[date] = mapped_column(Date, index=True)
