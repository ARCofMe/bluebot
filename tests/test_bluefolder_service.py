from datetime import date
from types import SimpleNamespace

from app.services.bluefolder_service import BlueFolderService
from app.core.config import settings


class DummyAssignmentsClient:
    def __init__(self, rows):
        self.rows = rows
        self.calls = []

    def list_for_user_range(self, user_id, start_date, end_date, date_range_type="scheduled"):
        self.calls.append(
            {
                "user_id": user_id,
                "start_date": start_date,
                "end_date": end_date,
                "date_range_type": date_range_type,
            }
        )
        return list(self.rows)


def _service() -> BlueFolderService:
    svc = BlueFolderService.__new__(BlueFolderService)
    svc._assignment_cache = {}
    return svc


def test_resolve_tech_id_prefers_env_mapping(monkeypatch):
    svc = _service()
    monkeypatch.setattr(settings, "discord_tech_map", '{"42":33538043}')
    assert svc.resolve_tech_id(42, ["Tech Name"]) == 33538043


def test_resolve_tech_id_matches_unique_candidate_name(monkeypatch):
    svc = _service()
    monkeypatch.setattr(settings, "discord_tech_map", None)
    monkeypatch.setattr(
        BlueFolderService,
        "list_active_techs",
        lambda self: [
            {"id": 11, "name": "Mike Smith"},
            {"id": 12, "name": "John Doe"},
        ],
    )

    assert svc.resolve_tech_id(7, ["mike smith", "Other"]) == 11


def test_resolve_tech_id_returns_none_for_ambiguous_name(monkeypatch):
    svc = _service()
    monkeypatch.setattr(settings, "discord_tech_map", None)
    monkeypatch.setattr(
        BlueFolderService,
        "list_active_techs",
        lambda self: [
            {"id": 11, "name": "Mike Smith"},
            {"id": 12, "name": "Mike Smith"},
        ],
    )

    assert svc.resolve_tech_id(7, ["Mike Smith"]) is None


def test_get_assignments_for_user_day_uses_cache(monkeypatch):
    svc = _service()
    rows = [
        {"assignmentId": 1, "serviceRequestId": 222, "start": "2026-03-21T09:00:00", "end": "2026-03-21T10:00:00", "isComplete": False},
    ]
    assignments = DummyAssignmentsClient(rows)
    svc.client = SimpleNamespace(assignments=assignments)
    monkeypatch.setattr(BlueFolderService, "_enrich_assignments", lambda self, items: [{"assignment_id": 1, "service_request_id": 222}])
    monkeypatch.setattr(settings, "assignment_cache_ttl_seconds", 120)

    first = svc.get_assignments_for_user_day(10, date(2026, 3, 21))
    second = svc.get_assignments_for_user_day(10, date(2026, 3, 21))

    assert first == second == [{"assignment_id": 1, "service_request_id": 222}]
    assert len(assignments.calls) == 1


def test_workflow_targets_follow_settings(monkeypatch):
    svc = _service()
    monkeypatch.setattr(settings, "workflow_write_assignment", True)
    monkeypatch.setattr(settings, "workflow_write_sr_note", False)
    assert svc._workflow_targets() == ["assignment"]

    monkeypatch.setattr(settings, "workflow_write_assignment", False)
    monkeypatch.setattr(settings, "workflow_write_sr_note", True)
    assert svc._workflow_targets() == ["sr_note"]


def test_write_workflow_update_returns_error_when_all_targets_disabled(monkeypatch):
    svc = _service()
    monkeypatch.setattr(settings, "workflow_write_assignment", False)
    monkeypatch.setattr(settings, "workflow_write_sr_note", False)

    result = svc._write_workflow_update(123, user_id=10, assignment_id=20, text="hello")

    assert result["ok"] is False
    assert "disabled" in result["error"]


def test_mark_enroute_writes_eta_when_minutes_provided(monkeypatch):
    svc = _service()
    monkeypatch.setattr(BlueFolderService, "get_assignment_for_sr_in_workflow_window", lambda self, user_id, sr_id: {"assignment_id": 55})
    calls = []

    def fake_write(self, sr_id, *, user_id, assignment_id, text, complete_assignment=False):
        calls.append(
            {
                "sr_id": sr_id,
                "user_id": user_id,
                "assignment_id": assignment_id,
                "text": text,
                "complete_assignment": complete_assignment,
            }
        )
        return {"ok": True, "stored_as": "assignment + sr_note"}

    monkeypatch.setattr(BlueFolderService, "_write_workflow_update", fake_write)

    result = svc.mark_enroute(12345, user_id=10, minutes=20)

    assert result["ok"] is True
    assert result["assignment_id"] == 55
    assert result["eta_minutes"] == 20
    assert len(calls) == 2
    assert "Technician en route" in calls[0]["text"]
    assert calls[1]["text"] == "ETA update: arriving in 20 minutes."


def test_mark_enroute_returns_eta_failure(monkeypatch):
    svc = _service()
    monkeypatch.setattr(BlueFolderService, "get_assignment_for_sr_in_workflow_window", lambda self, user_id, sr_id: {"assignment_id": 55})
    calls = []

    def fake_write(self, sr_id, *, user_id, assignment_id, text, complete_assignment=False):
        calls.append(text)
        if text.startswith("ETA update"):
            return {"ok": False, "error": "write failed"}
        return {"ok": True, "stored_as": "assignment"}

    monkeypatch.setattr(BlueFolderService, "_write_workflow_update", fake_write)

    result = svc.mark_enroute(12345, user_id=10, minutes=20)

    assert result == {"ok": False, "error": "write failed"}
    assert len(calls) == 2
