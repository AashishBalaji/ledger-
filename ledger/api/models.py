"""SQLAlchemy ORM models: SKUs, demand observations, and policy run history."""
from __future__ import annotations

import datetime

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ledger.api.db import Base


class SKU(Base):
    __tablename__ = "skus"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(256), default="")
    unit_cost: Mapped[float] = mapped_column(Float)
    order_cost: Mapped[float] = mapped_column(Float)
    holding_cost_rate: Mapped[float] = mapped_column(Float)  # fraction of unit_cost / year
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC)
    )

    demand_observations: Mapped[list[DemandObservation]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )
    policy_runs: Mapped[list[PolicyRun]] = relationship(
        back_populates="sku", cascade="all, delete-orphan"
    )


class DemandObservation(Base):
    __tablename__ = "demand_observations"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), index=True)
    period_index: Mapped[int] = mapped_column()  # sequential period number, not a calendar date
    quantity: Mapped[float] = mapped_column(Float)

    sku: Mapped[SKU] = relationship(back_populates="demand_observations")


class PolicyRun(Base):
    """An audit record of a single policy computation (EOQ or safety stock),
    storing both the inputs used and the result, as JSON text — kept simple
    (String, not JSONB) so this works unchanged against either Postgres or
    SQLite in tests."""

    __tablename__ = "policy_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku_id: Mapped[int] = mapped_column(ForeignKey("skus.id"), index=True)
    policy_type: Mapped[str] = mapped_column(String(32))  # "eoq" | "safety_stock"
    inputs_json: Mapped[str] = mapped_column(String)
    result_json: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime.datetime] = mapped_column(
        default=lambda: datetime.datetime.now(datetime.UTC)
    )

    sku: Mapped[SKU] = relationship(back_populates="policy_runs")
