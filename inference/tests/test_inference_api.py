from __future__ import annotations

from pathlib import Path

import yaml
from borj_inference.main import create_app
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def news2_result_validator() -> Draft202012Validator:
    doc = yaml.safe_load((ROOT / "contracts" / "openapi.yaml").read_text(encoding="utf-8"))
    return Draft202012Validator({"$ref": "#/components/schemas/News2Result", "components": doc["components"]})


def test_batch_scores_each_bed_and_matches_contract():
    client = TestClient(create_app())
    body = {
        "asOf": "2026-10-10T22:10:00Z",
        "beds": [
            {"bed": "B04", "params": {
                "resp_rate": {"value": 22, "status": "fresh", "ageS": 399, "staleAfterS": 900},
                "pulse": {"value": 112, "status": "fresh", "ageS": 399, "staleAfterS": 900},
                "consciousness": {"value": "A", "status": "stale", "ageS": 20000, "staleAfterS": 14400},
            }},
            {"bed": "B05", "params": {}},
        ],
    }
    resp = client.post("/v1/news2/batch", json=body)
    assert resp.status_code == 200
    results = resp.json()["results"]

    validator = news2_result_validator()
    for result in results.values():
        assert not list(validator.iter_errors(result)), list(validator.iter_errors(result))
    assert results["B04"]["total"] == 4
    assert results["B04"]["stale"] == ["consciousness"]
    assert results["B05"]["confidence"]["value"] == 0.0


def test_rejects_bad_status():
    client = TestClient(create_app())
    body = {"asOf": "2026-10-10T22:10:00Z",
            "beds": [{"bed": "B04", "params": {"pulse": {"value": 80, "status": "guessed", "ageS": 1,
                                                          "staleAfterS": 900}}}]}
    assert client.post("/v1/news2/batch", json=body).status_code == 422


def test_every_parameter_block_names_its_validator():
    """Invariant 8: every clinical block in config says who must validate it."""
    cfg = yaml.safe_load((ROOT / "inference" / "config" / "news2.yaml").read_text(encoding="utf-8"))
    blocks = list(cfg["parameters"].values()) + [cfg["response"], cfg["confidence"]]
    assert all(block.get("validated_by") for block in blocks)
