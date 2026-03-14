"""BlueFolder service helpers for the Discord bot."""

from __future__ import annotations

import os
import sys
import xml.etree.ElementTree as ET
from datetime import date
from typing import Any

from app.core.config import settings


def _maybe_extend_sys_path() -> None:
    candidate = settings.bluefolder_api_path or "/home/ner0tic/Documents/Projects/ARCoM/bluefolder-api"
    if candidate and candidate not in sys.path:
        sys.path.append(candidate)


class BlueFolderService:
    """Small adapter over the local BlueFolder wrapper."""

    def __init__(self) -> None:
        _maybe_extend_sys_path()
        if settings.bluefolder_api_key:
            os.environ["BLUEFOLDER_API_KEY"] = settings.bluefolder_api_key
        if settings.bluefolder_account_name:
            os.environ["BLUEFOLDER_ACCOUNT_NAME"] = settings.bluefolder_account_name

        from bluefolder_api.client import BlueFolderClient  # type: ignore

        self.client = BlueFolderClient()

    def list_active_techs(self) -> list[dict[str, Any]]:
        techs = self.client.users.list_active()
        return [
            {
                "id": int(t.get("id") or t.get("userId")),
                "name": f"{t.get('firstName', '').strip()} {t.get('lastName', '').strip()}".strip(),
                "email": t.get("email"),
            }
            for t in techs
            if t.get("id") or t.get("userId")
        ]

    def get_assignments_for_user_today(self, user_id: int) -> list[dict[str, Any]]:
        assignments = self.client.assignments.list_for_user_today(user_id)
        results: list[dict[str, Any]] = []
        for a in assignments:
            sr_id = a.get("serviceRequestId")
            subject = None
            if sr_id:
                try:
                    sr_xml = self.client.service_requests.get_by_id(int(sr_id))
                    sr = sr_xml.find(".//serviceRequest")
                    if sr is not None:
                        subject = sr.findtext("description") or sr.findtext("subject")
                except Exception:
                    subject = None
            results.append(
                {
                    "assignment_id": a.get("assignmentId"),
                    "service_request_id": sr_id,
                    "subject": subject or "Service Request",
                    "start": a.get("start"),
                    "end": a.get("end"),
                    "is_complete": a.get("isComplete"),
                }
            )
        return results

    def get_service_request(self, sr_id: int) -> dict[str, Any]:
        sr_xml = self.client.service_requests.get_by_id(sr_id)
        sr = sr_xml.find(".//serviceRequest")
        if sr is None:
            return {}

        customer_id = sr.findtext("customerId")
        location_id = sr.findtext("customerLocationId")
        address = None
        if customer_id and location_id:
            try:
                loc_xml = self.client.customers.get_location_by_id(int(customer_id), int(location_id))
                loc = loc_xml.find(".//customerLocation")
                if loc is not None:
                    parts = [
                        loc.findtext("addressStreet"),
                        loc.findtext("addressCity"),
                        loc.findtext("addressState"),
                        loc.findtext("addressPostalCode"),
                    ]
                    address = ", ".join([p for p in parts if p])
            except Exception:
                address = None

        return {
            "id": sr.findtext("id") or str(sr_id),
            "subject": sr.findtext("description") or sr.findtext("subject") or "Service Request",
            "status": sr.findtext("status"),
            "priority": sr.findtext("priority"),
            "customer_id": customer_id,
            "location_id": location_id,
            "address": address,
        }
