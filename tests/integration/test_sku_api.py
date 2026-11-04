"""Integration tests for SKU CRUD + demand history, against a real Postgres DB."""


def test_create_and_get_sku(client):
    resp = client.post(
        "/skus",
        json={
            "sku_code": "WIDGET-001",
            "description": "Test widget",
            "unit_cost": 10.0,
            "order_cost": 50.0,
            "holding_cost_rate": 0.2,
        },
    )
    assert resp.status_code == 201
    created = resp.json()
    assert created["sku_code"] == "WIDGET-001"

    resp2 = client.get(f"/skus/{created['id']}")
    assert resp2.status_code == 200
    assert resp2.json()["sku_code"] == "WIDGET-001"


def test_duplicate_sku_code_rejected(client):
    payload = {
        "sku_code": "DUP-001",
        "unit_cost": 5.0,
        "order_cost": 25.0,
        "holding_cost_rate": 0.1,
    }
    first = client.post("/skus", json=payload)
    assert first.status_code == 201
    second = client.post("/skus", json=payload)
    assert second.status_code == 409


def test_get_nonexistent_sku_404(client):
    resp = client.get("/skus/999999")
    assert resp.status_code == 404


def test_list_skus(client):
    for code in ("A-1", "A-2", "A-3"):
        client.post(
            "/skus",
            json={"sku_code": code, "unit_cost": 1, "order_cost": 1, "holding_cost_rate": 0.1},
        )
    resp = client.get("/skus")
    assert resp.status_code == 200
    codes = {row["sku_code"] for row in resp.json()}
    assert codes == {"A-1", "A-2", "A-3"}


def test_add_demand_observations(client):
    created = client.post(
        "/skus",
        json={"sku_code": "DEM-1", "unit_cost": 1, "order_cost": 1, "holding_cost_rate": 0.1},
    ).json()
    resp = client.post(
        f"/skus/{created['id']}/demand",
        json={"observations": [{"period_index": 1, "quantity": 10.0}, {"period_index": 2, "quantity": 12.0}]},
    )
    assert resp.status_code == 201
    assert resp.json()["inserted"] == 2


def test_add_demand_to_nonexistent_sku_404(client):
    resp = client.post(
        "/skus/999999/demand",
        json={"observations": [{"period_index": 1, "quantity": 10.0}]},
    )
    assert resp.status_code == 404


def test_invalid_sku_payload_rejected(client):
    resp = client.post(
        "/skus",
        json={"sku_code": "BAD-1", "unit_cost": -5, "order_cost": 1, "holding_cost_rate": 0.1},
    )
    assert resp.status_code == 422
