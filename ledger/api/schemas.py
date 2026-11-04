"""Pydantic request/response schemas for the API layer."""
from __future__ import annotations

from pydantic import BaseModel, Field


class SKUCreate(BaseModel):
    sku_code: str
    description: str = ""
    unit_cost: float = Field(gt=0)
    order_cost: float = Field(gt=0)
    holding_cost_rate: float = Field(gt=0, lt=1)


class SKUOut(BaseModel):
    id: int
    sku_code: str
    description: str
    unit_cost: float
    order_cost: float
    holding_cost_rate: float

    model_config = {"from_attributes": True}


class DemandObservationIn(BaseModel):
    period_index: int
    quantity: float = Field(ge=0)


class DemandBatchIn(BaseModel):
    observations: list[DemandObservationIn]


class EOQRequest(BaseModel):
    annual_demand: float = Field(gt=0)
    order_cost: float | None = None  # falls back to SKU's stored order_cost
    holding_cost_per_unit: float | None = None  # falls back to SKU unit_cost * holding_cost_rate


class EOQResponse(BaseModel):
    order_quantity: float
    orders_per_year: float
    cycle_time_days: float
    annual_ordering_cost: float
    annual_holding_cost: float
    total_annual_cost: float


class SafetyStockRequest(BaseModel):
    mean_demand_per_period: float = Field(ge=0)
    std_demand_per_period: float = Field(ge=0)
    mean_lead_time_periods: float = Field(gt=0)
    std_lead_time_periods: float = Field(ge=0, default=0.0)
    service_level: float = Field(gt=0, lt=1, default=0.95)


class SafetyStockResponse(BaseModel):
    z_score: float
    demand_during_lead_time: float
    std_dev_during_lead_time: float
    safety_stock: float
    reorder_point: float


class EchelonNodeIn(BaseModel):
    node_id: str
    mean_lead_time_periods: float = Field(gt=0)
    std_lead_time_periods: float = Field(ge=0, default=0.0)
    service_level: float = Field(gt=0, lt=1, default=0.95)
    mean_demand_per_period: float = Field(ge=0, default=0.0)
    std_demand_per_period: float = Field(ge=0, default=0.0)
    children: list[EchelonNodeIn] = Field(default_factory=list)


class NetworkSafetyStockNodeOut(BaseModel):
    node_id: str
    aggregated_mean_demand: float
    aggregated_std_demand: float
    safety_stock: SafetyStockResponse


class NetworkSafetyStockResponse(BaseModel):
    nodes: list[NetworkSafetyStockNodeOut]
    total_network_safety_stock: float
