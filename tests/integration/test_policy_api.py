"""Integration tests for the EOQ, safety-stock, and network endpoints,
against a real Postgres DB and real HTTP layer — confirms the API wiring
produces the same numbers as the unit-tested engine, plus that policy runs
are actually persisted as an audit trail."""
import pytest

from ledger.api.db import SessionLocal
from ledger.api.models import PolicyRun


def _make_sku(client, **overrides):
    payload = {
        "sku_code": "EOQ-SKU",
        "unit_cost": 10.0,
        "order_cost": 50.0,
        "holding_cost_rate": 0.2,
    }
    payload.update(overrides)
    resp = client.post("/skus", json=payload)
    assert resp.status_code == 201
    return resp.json()


def test_eoq_endpoint_uses_sku_defaults(client):
    sku = _make_sku(client)
    resp = client.post(f"/skus/{sku['id']}/eoq", json={"annual_demand": 1000})
    assert resp.status_code == 200
    body = resp.json()
    # holding_cost = unit_cost * holding_cost_rate = 10 * 0.2 = 2
    # Q* = sqrt(2*1000*50/2) = 223.6068
    assert body["order_quantity"] == pytest.approx(223.6068, rel=1e-4)


def test_eoq_endpoint_override_costs(client):
    sku = _make_sku(client)
    resp = client.post(
        f"/skus/{sku['id']}/eoq",
        json={"annual_demand": 1000, "order_cost": 50, "holding_cost_per_unit": 2},
    )
    assert resp.status_code == 200
    assert resp.json()["order_quantity"] == pytest.approx(223.6068, rel=1e-4)


def test_eoq_endpoint_persists_policy_run(client):
    sku = _make_sku(client)
    client.post(f"/skus/{sku['id']}/eoq", json={"annual_demand": 1000})

    db = SessionLocal()
    try:
        runs = db.query(PolicyRun).filter_by(sku_id=sku["id"], policy_type="eoq").all()
        assert len(runs) == 1
    finally:
        db.close()


def test_eoq_endpoint_404_for_missing_sku(client):
    resp = client.post("/skus/999999/eoq", json={"annual_demand": 1000})
    assert resp.status_code == 404


def test_safety_stock_endpoint(client):
    sku = _make_sku(client)
    resp = client.post(
        f"/skus/{sku['id']}/safety-stock",
        json={
            "mean_demand_per_period": 2500,
            "std_demand_per_period": 500,
            "mean_lead_time_periods": 2,
            "std_lead_time_periods": 0.0,
            "service_level": 0.90,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["reorder_point"] == pytest.approx(5906.3, rel=1e-3)


def test_safety_stock_endpoint_persists_policy_run(client):
    sku = _make_sku(client)
    client.post(
        f"/skus/{sku['id']}/safety-stock",
        json={
            "mean_demand_per_period": 100,
            "std_demand_per_period": 20,
            "mean_lead_time_periods": 1,
        },
    )
    db = SessionLocal()
    try:
        runs = db.query(PolicyRun).filter_by(sku_id=sku["id"], policy_type="safety_stock").all()
        assert len(runs) == 1
    finally:
        db.close()


def test_network_safety_stock_endpoint_two_tier(client):
    """Stateless network endpoint, no SKU needed — exercises the full
    HTTP -> pydantic -> engine -> pydantic round trip for a 3-node tree."""
    resp = client.post(
        "/network/safety-stock",
        json={
            "node_id": "dc",
            "mean_lead_time_periods": 5,
            "service_level": 0.95,
            "children": [
                {
                    "node_id": "wh-a",
                    "mean_lead_time_periods": 1,
                    "service_level": 0.95,
                    "mean_demand_per_period": 100,
                    "std_demand_per_period": 20,
                },
                {
                    "node_id": "wh-b",
                    "mean_lead_time_periods": 1,
                    "service_level": 0.95,
                    "mean_demand_per_period": 100,
                    "std_demand_per_period": 20,
                },
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    node_ids = {n["node_id"] for n in body["nodes"]}
    assert node_ids == {"dc", "wh-a", "wh-b"}
    dc_node = next(n for n in body["nodes"] if n["node_id"] == "dc")
    assert dc_node["aggregated_mean_demand"] == pytest.approx(200)
    assert body["total_network_safety_stock"] == pytest.approx(
        sum(n["safety_stock"]["safety_stock"] for n in body["nodes"])
    )


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
