"""FastAPI service: REST endpoints over the inventory optimization engine."""
from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from ledger.api import models, schemas
from ledger.api.db import Base, engine, get_db
from ledger.network.multi_echelon import (
    EchelonNode,
    propagate_safety_stock,
    total_network_safety_stock,
)
from ledger.policies.eoq import EOQInputs, classic_eoq
from ledger.policies.safety_stock import DemandLeadTimeInputs, safety_stock_and_reorder_point


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title="Ledger",
    description="Inventory optimization engine: EOQ, safety stock, and multi-echelon placement.",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# --- SKUs -------------------------------------------------------------


@app.post("/skus", response_model=schemas.SKUOut, status_code=201)
def create_sku(payload: schemas.SKUCreate, db: Session = Depends(get_db)) -> models.SKU:
    existing = db.query(models.SKU).filter_by(sku_code=payload.sku_code).first()
    if existing:
        raise HTTPException(status_code=409, detail="sku_code already exists")
    sku = models.SKU(**payload.model_dump())
    db.add(sku)
    db.commit()
    db.refresh(sku)
    return sku


@app.get("/skus", response_model=list[schemas.SKUOut])
def list_skus(db: Session = Depends(get_db)) -> list[models.SKU]:
    return db.query(models.SKU).order_by(models.SKU.id).all()


@app.get("/skus/{sku_id}", response_model=schemas.SKUOut)
def get_sku(sku_id: int, db: Session = Depends(get_db)) -> models.SKU:
    sku = db.get(models.SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")
    return sku


# --- Demand history -----------------------------------------------------


@app.post("/skus/{sku_id}/demand", status_code=201)
def add_demand_observations(
    sku_id: int, payload: schemas.DemandBatchIn, db: Session = Depends(get_db)
) -> dict[str, int]:
    sku = db.get(models.SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    rows = [
        models.DemandObservation(sku_id=sku_id, period_index=obs.period_index, quantity=obs.quantity)
        for obs in payload.observations
    ]
    db.add_all(rows)
    db.commit()
    return {"inserted": len(rows)}


# --- Policy endpoints -----------------------------------------------------


@app.post("/skus/{sku_id}/eoq", response_model=schemas.EOQResponse)
def compute_eoq(
    sku_id: int, payload: schemas.EOQRequest, db: Session = Depends(get_db)
) -> schemas.EOQResponse:
    sku = db.get(models.SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    order_cost = payload.order_cost if payload.order_cost is not None else sku.order_cost
    holding_cost = (
        payload.holding_cost_per_unit
        if payload.holding_cost_per_unit is not None
        else sku.unit_cost * sku.holding_cost_rate
    )

    inputs = EOQInputs(
        annual_demand=payload.annual_demand,
        order_cost=order_cost,
        holding_cost_per_unit=holding_cost,
    )
    result = classic_eoq(inputs)

    db.add(
        models.PolicyRun(
            sku_id=sku_id,
            policy_type="eoq",
            inputs_json=json.dumps(payload.model_dump()),
            result_json=json.dumps(result.__dict__),
        )
    )
    db.commit()

    return schemas.EOQResponse(**result.__dict__)


@app.post("/skus/{sku_id}/safety-stock", response_model=schemas.SafetyStockResponse)
def compute_safety_stock(
    sku_id: int, payload: schemas.SafetyStockRequest, db: Session = Depends(get_db)
) -> schemas.SafetyStockResponse:
    sku = db.get(models.SKU, sku_id)
    if sku is None:
        raise HTTPException(status_code=404, detail="SKU not found")

    inputs = DemandLeadTimeInputs(**payload.model_dump())
    result = safety_stock_and_reorder_point(inputs)

    db.add(
        models.PolicyRun(
            sku_id=sku_id,
            policy_type="safety_stock",
            inputs_json=json.dumps(payload.model_dump()),
            result_json=json.dumps(result.__dict__),
        )
    )
    db.commit()

    return schemas.SafetyStockResponse(**result.__dict__)


# --- Network (multi-echelon) endpoint — stateless, no DB needed ----------


def _to_engine_node(node_in: schemas.EchelonNodeIn) -> EchelonNode:
    node = EchelonNode(
        node_id=node_in.node_id,
        mean_lead_time_periods=node_in.mean_lead_time_periods,
        std_lead_time_periods=node_in.std_lead_time_periods,
        service_level=node_in.service_level,
        mean_demand_per_period=node_in.mean_demand_per_period,
        std_demand_per_period=node_in.std_demand_per_period,
    )
    node.children = [_to_engine_node(c) for c in node_in.children]
    return node


@app.post("/network/safety-stock", response_model=schemas.NetworkSafetyStockResponse)
def compute_network_safety_stock(
    root: schemas.EchelonNodeIn,
) -> schemas.NetworkSafetyStockResponse:
    engine_root = _to_engine_node(root)
    reports = propagate_safety_stock(engine_root)

    nodes_out = [
        schemas.NetworkSafetyStockNodeOut(
            node_id=r.node_id,
            aggregated_mean_demand=r.aggregated_mean_demand,
            aggregated_std_demand=r.aggregated_std_demand,
            safety_stock=schemas.SafetyStockResponse(**r.safety_stock.__dict__),
        )
        for r in reports.values()
    ]

    return schemas.NetworkSafetyStockResponse(
        nodes=nodes_out,
        total_network_safety_stock=total_network_safety_stock(reports),
    )
