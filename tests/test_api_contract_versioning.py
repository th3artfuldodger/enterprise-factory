from web.backend.middleware.api_version import canonical_api_path

def test_v1_paths_canonicalize_to_unversioned_api():
    assert canonical_api_path("/api/v1/customer/factory") == "/api/customer/factory"
    assert canonical_api_path("/api/v1/health/ready") == "/api/health/ready"
    assert canonical_api_path("/api/customer/factory") == "/api/customer/factory"

def test_stable_contract_snapshot_has_no_missing_routes():
    import json
    from pathlib import Path
    doc=json.loads((Path(__file__).parents[1]/"docs/api-contract-v1.json").read_text())
    assert doc["contract"] == "factory-v1"
    assert doc["missing"] == []
    assert len(doc["required"]) >= 11
