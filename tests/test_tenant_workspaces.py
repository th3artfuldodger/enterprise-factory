from web.backend.services import tenant_workspaces as tenants


def test_customer_workspaces_are_deterministic_and_isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path)

    a = "cust-alpha"
    b = "cust-beta"
    assert tenants.customer_workspace_id(a) == tenants.customer_workspace_id(a)
    assert tenants.customer_workspace_id(a) != tenants.customer_workspace_id(b)

    tenants.write_customer_product(a, {"id": "prod-alpha1234", "idea": "A", "state": "IDEA_RECEIVED"})
    tenants.write_customer_product(b, {"id": "prod-beta12345", "idea": "B", "state": "IDEA_RECEIVED"})

    state_a = tenants.read_customer_pipeline_state(a)
    state_b = tenants.read_customer_pipeline_state(b)

    assert set(state_a["products"]) == {"prod-alpha1234"}
    assert set(state_b["products"]) == {"prod-beta12345"}
    assert state_a["workspace_id"] != state_b["workspace_id"]
    assert tenants.tenant_pipeline_db(a) != tenants.tenant_pipeline_db(b)


def test_customer_product_is_stamped_with_tenant_workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(tenants, "data_root", lambda: tmp_path)
    row = tenants.write_customer_product(
        "cust-one",
        {"id": "prod-tenant1234", "idea": "Build it", "state": "IDEA_RECEIVED", "metadata": {}},
    )
    ws = tenants.customer_workspace_id("cust-one")
    assert row["workspace_id"] == ws
    assert row["metadata"]["tenant_workspace_id"] == ws
    assert row["metadata"]["owner_customer_id"] == "cust-one"


def test_tenant_worker_preserves_explicit_provider_config(tmp_path, monkeypatch):
    from tenant_worker_supervisor import _env_for

    tenant_root = tmp_path / "customer-test"
    (tenant_root / "state").mkdir(parents=True)
    explicit = tmp_path / "shared-provider.yaml"
    explicit.write_text("default_provider: local_ollama\n", encoding="utf-8")
    monkeypatch.setenv("AIFACTORY_MODEL_PROVIDERS", str(explicit))

    env = _env_for(tenant_root)

    assert env["AIFACTORY_MODEL_PROVIDERS"] == str(explicit)
    assert env["AIFACTORY_DATA_ROOT"] == str(tenant_root)
