"""canli demo: butce kapsami, butce kayitlari, demo istekleri ve ziyaretci kullanicilar

Yalnizca EKLEME yapar (yeni tablolar, yeni sutunlar, genisletilmis bir CHECK kisiti); mevcut veri
silinmez veya degistirilmez.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-08 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003"
down_revision: str | Sequence[str] | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD_OUTCOMES = (
    "'decided', 'skipped_not_new', 'skipped_human_edit', 'failed_provider', "
    "'failed_error', 'failed_worker_lost'"
)
NEW_OUTCOMES = OLD_OUTCOMES + ", 'provider_uncertain', 'budget_exhausted'"


def upgrade() -> None:
    # --- ziyaretci kullanicilar ---
    op.add_column(
        "users", sa.Column("is_demo", sa.Boolean(), server_default="false", nullable=False)
    )
    op.add_column("users", sa.Column("demo_ip_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_users_is_demo_created_at", "users", ["is_demo", "created_at"], unique=False)

    # --- karar isi sonuclari: iki yeni deger (kisit genisletilir) ---
    op.drop_constraint(op.f("ck_decision_jobs_outcome"), "decision_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_decision_jobs_outcome"), "decision_jobs", f"outcome IN ({NEW_OUTCOMES})"
    )

    # --- butce kapsami ve kayitlari ---
    op.create_table(
        "budgets",
        sa.Column("id", sa.String(length=60), nullable=False),
        sa.Column("cap_usd", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column("purpose", sa.String(length=200), server_default="", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("cap_usd > 0", name=op.f("ck_budgets_cap_positive")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budgets")),
    )
    op.create_table(
        "budget_entries",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False, start=1), nullable=False),
        sa.Column("budget_id", sa.String(length=60), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("model", sa.String(length=100), nullable=False),
        sa.Column("price_version", sa.String(length=300), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(precision=20, scale=10), nullable=False),
        sa.Column(
            "reserved_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=10), server_default="pending", nullable=False),
        sa.Column("charge_usd", sa.Numeric(precision=20, scale=10), nullable=True),
        sa.Column("known", sa.Boolean(), nullable=True),
        sa.Column("exceeded_reservation", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("reserved_usd > 0", name=op.f("ck_budget_entries_reserved_positive")),
        sa.CheckConstraint(
            "state = 'pending' OR (charge_usd IS NOT NULL AND known IS NOT NULL)",
            name=op.f("ck_budget_entries_settled_has_charge"),
        ),
        sa.CheckConstraint("state IN ('pending', 'settled')", name=op.f("ck_budget_entries_state")),
        sa.ForeignKeyConstraint(
            ["budget_id"], ["budgets.id"], name=op.f("fk_budget_entries_budget_id_budgets")
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["decision_jobs.id"],
            name=op.f("fk_budget_entries_job_id_decision_jobs"),
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_budget_entries")),
    )
    op.create_index(
        "ix_budget_entries_budget_id_state", "budget_entries", ["budget_id", "state"], unique=False
    )
    op.create_index("ix_budget_entries_job_id", "budget_entries", ["job_id"], unique=False)

    # --- demo istekleri (tekrar-gonderme anahtari) ---
    op.create_table(
        "demo_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ticket_id", sa.Uuid(), nullable=False),
        sa.Column("request_key", sa.String(length=64), nullable=False),
        sa.Column("ip_hash", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["ticket_id"],
            ["tickets.id"],
            name=op.f("fk_demo_requests_ticket_id_tickets"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_demo_requests_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_demo_requests")),
        sa.UniqueConstraint("user_id", "request_key", name=op.f("uq_demo_requests_user_id")),
    )
    op.create_index("ix_demo_requests_created_at", "demo_requests", ["created_at"], unique=False)
    op.create_index(
        "ix_demo_requests_ip_hash_created_at",
        "demo_requests",
        ["ip_hash", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_demo_requests_ip_hash_created_at", table_name="demo_requests")
    op.drop_index("ix_demo_requests_created_at", table_name="demo_requests")
    op.drop_table("demo_requests")
    op.drop_index("ix_budget_entries_job_id", table_name="budget_entries")
    op.drop_index("ix_budget_entries_budget_id_state", table_name="budget_entries")
    op.drop_table("budget_entries")
    op.drop_table("budgets")

    # Eski kisit yeni degerleri kabul etmez: bu degerli isler (yalnizca canli demoda olusur) eski,
    # en yakin degere cevrilir. Ziyaretci kullanicilar ve talepleri silinmez; yalnizca isaretleri gider.
    op.execute(
        "UPDATE decision_jobs SET outcome = 'failed_provider' "
        "WHERE outcome IN ('provider_uncertain', 'budget_exhausted')"
    )
    op.drop_constraint(op.f("ck_decision_jobs_outcome"), "decision_jobs", type_="check")
    op.create_check_constraint(
        op.f("ck_decision_jobs_outcome"), "decision_jobs", f"outcome IN ({OLD_OUTCOMES})"
    )

    op.drop_index("ix_users_is_demo_created_at", table_name="users")
    op.drop_column("users", "demo_ip_hash")
    op.drop_column("users", "is_demo")
