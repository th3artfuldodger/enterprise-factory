import pytest

from web.backend.services import factory_personnel as personnel


def test_funding_ai_can_request_but_not_approve_money(tmp_path, monkeypatch):
    monkeypatch.setattr(personnel, "_path", lambda: tmp_path / "factory_personnel.json")
    roster = personnel.personnel_map()
    sales = roster["sales"]
    assert "request_funding" in sales["permissions"]
    assert "approve_funding" not in sales["permissions"]


@pytest.mark.parametrize(
    "permission",
    [
        "approve_funding",
        "spend_money",
        "transfer_funds",
        "borrow_money",
        "invest_funds",
        "contract_authority",
        "sign_contract",
        "payout_funds",
    ],
)
def test_financial_authority_cannot_be_granted_to_ai(tmp_path, monkeypatch, permission):
    monkeypatch.setattr(personnel, "_path", lambda: tmp_path / "factory_personnel.json")
    manager = personnel.create_personnel(
        "Manager who oversees research workers",
        role_class="manager",
        label="Research Manager",
    )
    with pytest.raises(ValueError, match="Factory Constitution"):
        personnel.update_personnel(
            manager["id"],
            action="grant_permission",
            permission=permission,
        )


def test_legacy_forbidden_permissions_are_stripped_on_read(tmp_path, monkeypatch):
    path = tmp_path / "factory_personnel.json"
    monkeypatch.setattr(personnel, "_path", lambda: path)
    path.write_text(
        '{"version":1,"profiles":{"sales":{"permissions":["request_funding","approve_funding","spend_money"]}}}',
        encoding="utf-8",
    )
    sales = personnel.personnel_map()["sales"]
    assert sales["permissions"] == ["request_funding"]
