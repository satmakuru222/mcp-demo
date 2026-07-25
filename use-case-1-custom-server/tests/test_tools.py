import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from server import get_deployment_status


def test_get_deployment_status_known_service():
    result = get_deployment_status("checkout-api")
    assert result["service"] == "checkout-api"
    assert result["status"] == "healthy"
    assert "version" in result


def test_get_deployment_status_unknown_service_raises():
    import pytest

    with pytest.raises(ValueError, match="Unknown service"):
        get_deployment_status("nonexistent-service")


from server import search_knowledge_base


def test_search_knowledge_base_finds_match():
    results = search_knowledge_base("PagerDuty")
    assert len(results) == 1
    assert results[0]["file"] == "incident_response.md"
    assert "pagerduty" in results[0]["snippet"].lower()


def test_search_knowledge_base_no_match():
    results = search_knowledge_base("xyzxyzxyz-not-a-real-term")
    assert results == []


def test_search_knowledge_base_empty_query_raises():
    import pytest

    with pytest.raises(ValueError, match="must not be empty"):
        search_knowledge_base("   ")


import json


def test_create_support_ticket_appends_and_returns_id(tmp_path, monkeypatch):
    import server

    fake_tickets_file = tmp_path / "tickets.json"
    monkeypatch.setattr(server, "TICKETS_FILE", fake_tickets_file)

    from server import create_support_ticket

    ticket = create_support_ticket(
        "Disk full", "inventory-worker host is out of disk space"
    )

    assert ticket["id"] == 1
    assert ticket["title"] == "Disk full"
    assert ticket["status"] == "open"
    assert fake_tickets_file.exists()

    saved = json.loads(fake_tickets_file.read_text())
    assert len(saved) == 1
    assert saved[0]["title"] == "Disk full"


def test_create_support_ticket_empty_title_raises(tmp_path, monkeypatch):
    import server
    import pytest

    monkeypatch.setattr(server, "TICKETS_FILE", tmp_path / "tickets.json")

    from server import create_support_ticket

    with pytest.raises(ValueError, match="must not be empty"):
        create_support_ticket("   ", "some description")
