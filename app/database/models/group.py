from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    DateTime,
    Enum,
    ForeignKey,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.database.models.user import User


class MemberRole(StrEnum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class Group(TimestampMixin, Base):
    __tablename__ = "groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True)
    title: Mapped[str | None] = mapped_column(String(255))


class GroupMember(Base):
    __tablename__ = "group_members"
    __table_args__ = (UniqueConstraint("user_id", "group_id", name="uq_group_member"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    group_id: Mapped[int] = mapped_column(
        ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[MemberRole] = mapped_column(
        Enum(MemberRole, native_enum=False),
        default=MemberRole.MEMBER,
        nullable=False,
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    user: Mapped["User"] = relationship(back_populates="memberships")
    group: Mapped[Group] = relationship()
