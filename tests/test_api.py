"""API smoke tests using FastAPI's in-process TestClient (no network)."""

import json
import os

from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)

_SAMPLE_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "sample_company.json")


def _sample_base() -> dict:
    with open(_SAMPLE_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_valuation_post():
    body = {"base": _sample_base(), "revenue_growth": 0.06, "current_price": 30, "beta": 1.1}
    r = client.post("/valuation", json=body)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["invested_capital"] == 1_800_000
    assert data["result"]["target_price"] > 0
    assert data["upside"] is not None


def test_valuation_bad_terminal_growth():
    body = {"base": _sample_base(), "terminal_growth": 0.5, "wacc": 0.08}
    r = client.post("/valuation", json=body)
    assert r.status_code == 400  # WACC must exceed g


def test_sensitivity():
    body = {
        "valuation": {"base": _sample_base(), "wacc": 0.08},
        "wacc_values": [0.07, 0.08, 0.09],
        "growth_values": [0.02, 0.03],
    }
    r = client.post("/sensitivity", json=body)
    assert r.status_code == 200, r.text
    grid = r.json()
    assert len(grid["prices"]) == 3
    assert len(grid["prices"][0]) == 2
