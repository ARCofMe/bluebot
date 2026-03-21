from datetime import date
from types import SimpleNamespace
from xml.etree import ElementTree as ET

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


def test_list_active_techs_skips_invalid_rows_and_falls_back_name():
    svc = _service()
    svc.client = SimpleNamespace(
        users=SimpleNamespace(
            list_active=lambda: [
                {"id": "11", "firstName": "Mike", "lastName": "Smith", "email": "mike@example.com"},
                {"userId": "12"},
                {"id": "abc", "firstName": "Bad"},
                None,
            ]
        )
    )

    techs = svc.list_active_techs()

    assert techs == [
        {"id": 11, "name": "Mike Smith", "email": "mike@example.com"},
        {"id": 12, "name": "Tech 12", "email": None},
    ]


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


def test_enrich_assignments_skips_bad_sr_lookup_and_non_dict_rows():
    svc = _service()
    sr_xml = ET.fromstring(
        """
        <response>
          <serviceRequest>
            <description>Reach-in cooler warm</description>
          </serviceRequest>
        </response>
        """
    )
    svc.client = SimpleNamespace(
        service_requests=SimpleNamespace(get_by_id=lambda sr_id: sr_xml)
    )

    rows = svc._enrich_assignments(
        [
            {"assignmentId": 1, "serviceRequestId": "bad-id", "start": "2026-03-21T08:00:00", "end": "2026-03-21T09:00:00", "isComplete": False},
            {"assignmentId": 2, "serviceRequestId": "222", "start": "2026-03-21T09:00:00", "end": "2026-03-21T10:00:00", "isComplete": True},
            None,
        ]
    )

    assert len(rows) == 2
    assert rows[0]["assignment_id"] == 1
    assert rows[0]["subject"] == "Service Request"
    assert rows[1]["assignment_id"] == 2
    assert rows[1]["subject"] == "Reach-in cooler warm"


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


def test_bluefolder_ok_handles_fail_response_without_readable_error():
    svc = _service()

    class FailingResponse:
        attrib = {"status": "fail"}

        def findtext(self, pattern):
            raise RuntimeError("bad xml")

    result = svc._bluefolder_ok(FailingResponse())

    assert result == {"ok": False, "error": "BlueFolder rejected the request."}


def test_get_service_request_parses_customer_location_and_equipment(monkeypatch):
    svc = _service()
    sr_xml = ET.fromstring(
        """
        <response>
          <serviceRequest>
            <id>12345</id>
            <description>Refrigerator not cooling</description>
            <status>Open</status>
            <priority>High</priority>
            <customerId>77</customerId>
            <customerName>Acme Bakery</customerName>
            <customerContactFirstName>Jane</customerContactFirstName>
            <customerContactLastName>Owner</customerContactLastName>
            <customerContactPhone>207-555-0100</customerContactPhone>
            <customerContactEmail>jane@example.com</customerContactEmail>
            <customerLocationName>Main Shop</customerLocationName>
            <customerLocationStreetAddress>123 Main St</customerLocationStreetAddress>
            <customerLocationCity>Portland</customerLocationCity>
            <customerLocationState>ME</customerLocationState>
            <customerLocationPostalCode>04101</customerLocationPostalCode>
            <customerLocationNotes>Use side entrance</customerLocationNotes>
            <equipmentToService>
              <equipmentItem>
                <equipmentId>999</equipmentId>
                <equipName>Walk-In Cooler</equipName>
                <modelNo>ABC123</modelNo>
                <serialNo>SERIAL1</serialNo>
              </equipmentItem>
            </equipmentToService>
          </serviceRequest>
        </response>
        """
    )
    svc.client = SimpleNamespace(service_requests=SimpleNamespace(get_by_id=lambda sr_id: sr_xml))
    monkeypatch.setattr(BlueFolderService, "_location_dict", lambda self, customer_id, location_id: None)
    monkeypatch.setattr(BlueFolderService, "_customer_dict", lambda self, customer_id: None)

    result = svc.get_service_request(12345)

    assert result["id"] == "12345"
    assert result["subject"] == "Refrigerator not cooling"
    assert result["customer_name"] == "Acme Bakery"
    assert result["address"] == "123 Main St, Portland, ME, 04101"
    assert result["site_notes"] == "Use side entrance"
    assert result["contacts"][0]["name"] == "Jane Owner"
    assert result["equipment"][0]["name"] == "Walk-In Cooler"


def test_get_service_request_notes_strips_html_sorts_and_filters():
    svc = _service()
    history_xml = ET.fromstring(
        """
        <response>
          <serviceRequestHistory>
            <entryDate>2026-03-20T08:00:00</entryDate>
            <userName>Older Tech</userName>
            <entryType>Note</entryType>
            <comment>&lt;p&gt;Older&lt;br&gt;note&lt;/p&gt;</comment>
          </serviceRequestHistory>
          <serviceRequestHistory>
            <entryDate>2026-03-21T09:30:00</entryDate>
            <userName>Newer Tech</userName>
            <entryType>Diagnosis</entryType>
            <description>&lt;p&gt;Newest &lt;strong&gt;note&lt;/strong&gt;&lt;/p&gt;</description>
          </serviceRequestHistory>
          <serviceRequestHistory>
            <entryDate>2026-03-19T07:00:00</entryDate>
            <userName>Ignored</userName>
            <entryType>Note</entryType>
            <comment></comment>
          </serviceRequestHistory>
        </response>
        """
    )
    svc.client = SimpleNamespace(service_requests=SimpleNamespace(get_history=lambda sr_id: history_xml))

    notes = svc.get_service_request_notes(12345, limit=5)

    assert len(notes) == 2
    assert notes[0]["author"] == "Newer Tech"
    assert notes[0]["text"] == "Newest note"
    assert notes[1]["text"] == "Older\nnote"


def test_build_troubleshooting_summary_prefers_labor_sections(monkeypatch):
    svc = _service()
    monkeypatch.setattr(
        BlueFolderService,
        "get_service_request",
        lambda self, sr_id: {
            "id": "12345",
            "subject": "Dishwasher leaking",
            "customer_name": "Acme Bakery",
            "address": "123 Main St, Portland, ME, 04101",
        },
    )
    monkeypatch.setattr(
        BlueFolderService,
        "get_service_request_labor",
        lambda self, sr_id, limit=3: [
            {
                "description": "Customer Complaint: leaking badly\nDiagnosis: bad inlet valve\nWork Performed: replaced valve"
            }
        ],
    )
    monkeypatch.setattr(
        BlueFolderService,
        "get_service_request_notes",
        lambda self, sr_id, limit=8: [{"text": "Diagnosis: from notes only"}],
    )

    result = svc.build_troubleshooting_summary(12345)

    assert result["sections"]["complaint"] == "leaking badly"
    assert result["sections"]["diagnosis"] == "bad inlet valve"
    assert result["sections"]["work_performed"] == "replaced valve"
    assert "Customer Complaint" in result["source_text"]


def test_build_troubleshooting_summary_falls_back_to_notes(monkeypatch):
    svc = _service()
    monkeypatch.setattr(
        BlueFolderService,
        "get_service_request",
        lambda self, sr_id: {
            "id": "12345",
            "subject": "Washer noisy",
            "customer_name": "Acme Bakery",
            "address": "123 Main St, Portland, ME, 04101",
        },
    )
    monkeypatch.setattr(BlueFolderService, "get_service_request_labor", lambda self, sr_id, limit=3: [])
    monkeypatch.setattr(
        BlueFolderService,
        "get_service_request_notes",
        lambda self, sr_id, limit=8: [
            {"text": "Diagnosis: worn bearings\nParts Needed: tub kit"},
            {"text": "older note"},
        ],
    )

    result = svc.build_troubleshooting_summary(12345)

    assert result["sections"]["diagnosis"] == "worn bearings"
    assert result["sections"]["parts_needed"] == "tub kit"
    assert result["source_text"] == "Diagnosis: worn bearings\nParts Needed: tub kit"
