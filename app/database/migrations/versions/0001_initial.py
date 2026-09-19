"""initial schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-09-19

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "telegram_id",
            sa.BigInteger(),
            nullable=False,
            unique=True,
        ),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("first_name", sa.String(64), nullable=True),
        sa.Column("last_name", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(op.f("ix_users_telegram_id"), "users", ["telegram_id"])

    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "telegram_chat_id",
            sa.BigInteger(),
            nullable=False,
            unique=True,
        ),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_groups_telegram_chat_id"), "groups", ["telegram_chat_id"]
    )

    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("ADMIN", "MEMBER", name="memberrole", native_enum=False),
            nullable=False,
            server_default="MEMBER",
        ),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("user_id", "group_id", name="uq_group_member"),
    )
    op.create_index(
        op.f("ix_group_members_user_id"), "group_members", ["user_id"]
    )
    op.create_index(
        op.f("ix_group_members_group_id"), "group_members", ["group_id"]
    )

    op.create_table(
        "subjects",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("group_id", "name", name="uq_subject_group_name"),
    )
    op.create_index(
        op.f("ix_subjects_group_id"), "subjects", ["group_id"]
    )

    op.create_table(
        "homeworks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "group_id",
            sa.Integer(),
            sa.ForeignKey("groups.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subject_id",
            sa.Integer(),
            sa.ForeignKey("subjects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "author_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.String(4000), nullable=True),
        sa.Column("deadline", sa.Date(), nullable=False),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_homeworks_group_id"), "homeworks", ["group_id"]
    )
    op.create_index(
        op.f("ix_homeworks_subject_id"), "homeworks", ["subject_id"]
    )
    op.create_index(
        op.f("ix_homeworks_author_id"), "homeworks", ["author_id"]
    )
    op.create_index(
        op.f("ix_homeworks_deadline"), "homeworks", ["deadline"]
    )
    op.create_index(
        "ix_homeworks_group_deadline", "homeworks", ["group_id", "deadline"]
    )

    op.create_table(
        "attachments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "homework_id",
            sa.Integer(),
            sa.ForeignKey("homeworks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("telegram_file_id", sa.String(512), nullable=False),
        sa.Column(
            "file_type",
            sa.Enum("DOCUMENT", "PHOTO", name="attachmenttype", native_enum=False),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_attachments_homework_id"), "attachments", ["homework_id"]
    )

    op.create_table(
        "homework_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "homework_id",
            sa.Integer(),
            sa.ForeignKey("homeworks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("url", sa.String(2048), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        op.f("ix_homework_links_homework_id"),
        "homework_links",
        ["homework_id"],
    )


def downgrade() -> None:
    op.drop_table("homework_links")
    op.drop_table("attachments")
    op.drop_table("homeworks")
    op.drop_table("subjects")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("users")
