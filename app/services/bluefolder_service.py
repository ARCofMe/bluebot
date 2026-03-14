"""BlueFolder service helpers for the Discord bot."""

from __future__ import annotations

import html
import os
import re
import sys
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from app.core.config import settings


def _maybe_extend_sys_path() -> None:
    candidate = settings.bluefolder_api_path
    if candidate:
        resolved = Path(candidate).expanduser().resolve()
    else:
        resolved = (Path(__file__).resolve().parents[3] / "bluefolder-api").resolve()

    if resolved.exists() and str(resolved) not in sys.path:
        sys.path.append(str(resolved))


class BlueFolderService:
    """Small adapter over the local BlueFolder wrapper."""

    def __init__(self) -> None:
        _maybe_extend_sys_path()
        self._ensure_runtime_dependencies()
        if settings.bluefolder_api_key:
            os.environ["BLUEFOLDER_API_KEY"] = settings.bluefolder_api_key
        if settings.bluefolder_account_name:
            os.environ["BLUEFOLDER_ACCOUNT_NAME"] = settings.bluefolder_account_name
        if settings.bluefolder_base_url:
            os.environ["BLUEFOLDER_BASE_URL"] = settings.bluefolder_base_url
        if settings.bluefolder_host_header:
            os.environ["BLUEFOLDER_HOST_HEADER"] = settings.bluefolder_host_header
        if settings.bluefolder_verify_ssl is not None:
            os.environ["BLUEFOLDER_VERIFY_SSL"] = str(settings.bluefolder_verify_ssl).lower()
        if settings.bluefolder_timeout_seconds is not None:
            os.environ["BLUEFOLDER_TIMEOUT_SECONDS"] = str(settings.bluefolder_timeout_seconds)

        if settings.bluefolder_verify_ssl is False:
            self._suppress_insecure_request_warnings()

        from bluefolder_api.client import BlueFolderClient  # type: ignore

        client_kwargs = {}
        if settings.bluefolder_base_url:
            client_kwargs["base_url"] = settings.bluefolder_base_url
        self.client = BlueFolderClient(**client_kwargs)
        self._assignment_cache: dict[tuple[Any, ...], tuple[float, list[dict[str, Any]]]] = {}

    def _ensure_runtime_dependencies(self) -> None:
        """Fail fast when the HTTP client dependency is missing."""
        try:
            import requests  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Missing Python dependency 'requests'. Run `python -m pip install -r requirements.txt` in bluebot-discord-extension."
            ) from exc

    @staticmethod
    def _suppress_insecure_request_warnings() -> None:
        """Hide urllib3 TLS warnings for the current IP-based BlueFolder setup."""
        try:
            import urllib3

            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        except Exception:
            pass

    def _get_cached_assignments(self, key: tuple[Any, ...]) -> list[dict[str, Any]] | None:
        ttl = max(int(settings.assignment_cache_ttl_seconds), 0)
        if ttl <= 0:
            return None
        cached = self._assignment_cache.get(key)
        if not cached:
            return None
        cached_at, value = cached
        if time.monotonic() - cached_at > ttl:
            self._assignment_cache.pop(key, None)
            return None
        return value

    def _set_cached_assignments(self, key: tuple[Any, ...], value: list[dict[str, Any]]) -> None:
        ttl = max(int(settings.assignment_cache_ttl_seconds), 0)
        if ttl <= 0:
            return
        self._assignment_cache[key] = (time.monotonic(), value)

    def _clear_assignment_cache(self) -> None:
        self._assignment_cache.clear()

    @staticmethod
    def _clean_text(value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = " ".join(str(value).split())
        return cleaned or None

    @staticmethod
    def _clean_html_text(value: str | None) -> str | None:
        """Strip simple HTML and normalize whitespace for Discord display."""
        if value is None:
            return None

        text = str(value)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</li\s*>", "\n", text)
        text = re.sub(r"(?i)<li\s*>", "- ", text)
        text = re.sub(r"(?i)</p\s*>", "\n\n", text)
        text = re.sub(r"(?i)<p\s*>", "", text)
        text = re.sub(r"(?i)</?ul\s*>", "", text)
        text = re.sub(r"(?i)</?ol\s*>", "", text)
        text = re.sub(r"(?i)</?label\s*>", "", text)
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = "\n".join(line.strip() for line in text.splitlines())
        text = text.strip()
        return text or None

    @staticmethod
    def _safe_int(value: Any) -> int | None:
        try:
            return int(value)
        except Exception:
            return None

    @staticmethod
    def _format_dt(value: str | None) -> str | None:
        if not value:
            return None
        formats = (
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%dT%H:%M:%S.%f",
        )
        for fmt in formats:
            try:
                return datetime.strptime(value, fmt).strftime("%I:%M %p").lstrip("0")
            except Exception:
                continue
        return value

    @staticmethod
    def _safe_text(node: Any, tag: str) -> str | None:
        try:
            return node.findtext(tag)
        except Exception:
            return None

    @staticmethod
    def _split_name_parts(full_name: str | None) -> tuple[str, str]:
        """Split a display name into first/last parts for waiver URLs."""
        cleaned = " ".join((full_name or "").split()).strip()
        if not cleaned:
            return "", ""
        parts = cleaned.split(" ", 1)
        if len(parts) == 1:
            return parts[0], ""
        return parts[0], parts[1]

    def _location_dict(self, customer_id: str | None, location_id: str | None) -> dict[str, Any] | None:
        cid = self._safe_int(customer_id)
        lid = self._safe_int(location_id)
        if not cid or not lid:
            return None
        try:
            loc_xml = self.client.customers.get_location_by_id(cid, lid)
            loc = loc_xml.find(".//customerLocation")
            if loc is None:
                return None
            return {
                "name": self._safe_text(loc, "locationName"),
                "street": self._safe_text(loc, "addressStreet"),
                "city": self._safe_text(loc, "addressCity"),
                "state": self._safe_text(loc, "addressState"),
                "postal_code": self._safe_text(loc, "addressPostalCode"),
                "notes": self._safe_text(loc, "locationNotes"),
            }
        except Exception:
            return None

    @staticmethod
    def _equipment_from_sr(sr: Any) -> list[dict[str, Any]]:
        """Parse embedded equipment blocks from an SR payload."""
        items: list[dict[str, Any]] = []
        for node in sr.findall(".//equipmentToService/equipmentItem"):
            items.append(
                {
                    "id": node.findtext("equipmentId"),
                    "name": node.findtext("equipName"),
                    "model": node.findtext("modelNo"),
                    "serialNumber": node.findtext("serialNo"),
                    "manufacturer": node.findtext("mfrName"),
                    "type": node.findtext("equipType"),
                    "reference": node.findtext("refNo"),
                }
            )
        return items

    @staticmethod
    def _first_text(node: Any, tags: tuple[str, ...]) -> str | None:
        for tag in tags:
            value = node.findtext(tag)
            if value not in (None, ""):
                return value
        return None

    @classmethod
    def _materials_from_sr(cls, sr: Any) -> list[dict[str, Any]]:
        """Parse embedded material rows from a service request payload."""
        paths = (
            ".//materials/material",
            ".//materials/materialItem",
            ".//materialsToService/material",
            ".//materialsToService/materialItem",
            ".//serviceRequestMaterials/material",
            ".//serviceRequestMaterials/materialItem",
        )
        items: list[dict[str, Any]] = []
        seen_keys: set[tuple[str | None, str | None, str | None]] = set()
        for path in paths:
            for node in sr.findall(path):
                row = {
                    "id": cls._first_text(node, ("id", "materialId")),
                    "itemName": cls._first_text(
                        node,
                        ("itemName", "itemDescription", "description", "name"),
                    ),
                    "description": cls._first_text(
                        node,
                        ("description", "itemDescription", "comment"),
                    ),
                    "quantity": cls._first_text(node, ("quantity", "itemQuantity", "qty")),
                    "unitPrice": cls._first_text(node, ("unitPrice", "price", "rate")),
                    "total": cls._first_text(node, ("total", "lineTotal", "amount")),
                    "isBillable": cls._first_text(node, ("isBillable", "billable")),
                }
                key = (row["id"], row["itemName"], row["quantity"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                items.append(row)
        return items

    @classmethod
    def _labor_from_sr(cls, sr: Any) -> list[dict[str, Any]]:
        """Parse embedded labor rows from a service request payload."""
        paths = (
            ".//labor/labor",
            ".//labor/laborItem",
            ".//laborToService/labor",
            ".//laborToService/laborItem",
            ".//serviceRequestLabor/labor",
            ".//serviceRequestLabor/laborItem",
        )
        items: list[dict[str, Any]] = []
        seen_keys: set[tuple[str | None, str | None, str | None]] = set()
        for path in paths:
            for node in sr.findall(path):
                row = {
                    "id": cls._first_text(node, ("id", "laborId")),
                    "userId": cls._first_text(node, ("userId",)),
                    "date": cls._first_text(node, ("dateWorked", "date", "entryDate")),
                    "hours": cls._first_text(node, ("hoursWorked", "hours", "duration")),
                    "rate": cls._first_text(node, ("hourlyRate", "rate")),
                    "total": cls._first_text(node, ("total", "lineTotal", "amount")),
                    "isBillable": cls._first_text(node, ("isBillable", "billable")),
                    "description": cls._first_text(
                        node,
                        ("description", "comment", "itemDescription"),
                    ),
                }
                key = (row["id"], row["date"], row["hours"])
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                items.append(row)
        return items

    def _customer_dict(self, customer_id: str | None) -> dict[str, Any] | None:
        cid = self._safe_int(customer_id)
        if not cid:
            return None
        try:
            cust_xml = self.client.customers.get_by_id(cid)
            customer = cust_xml.find(".//customer")
            if customer is None:
                return None
            return {
                "id": self._safe_text(customer, "customerId") or str(cid),
                "name": self._safe_text(customer, "customerName") or self._safe_text(customer, "name"),
                "phone": self._safe_text(customer, "phone"),
                "email": self._safe_text(customer, "email"),
            }
        except Exception:
            return None

    def list_active_techs(self) -> list[dict[str, Any]]:
        techs = self.client.users.list_active()
        results = [
            {
                "id": int(t.get("id") or t.get("userId")),
                "name": f"{t.get('firstName', '').strip()} {t.get('lastName', '').strip()}".strip(),
                "email": t.get("email"),
            }
            for t in techs
            if t.get("id") or t.get("userId")
        ]
        return sorted(results, key=lambda item: item["name"].casefold())

    def get_user(self, user_id: int) -> dict[str, Any]:
        try:
            user = self.client.users.get_by_id(user_id)
        except Exception as exc:
            return {"id": str(user_id), "error": str(exc)}
        if not user:
            try:
                users = self.client.users.list_all()
            except Exception:
                return {}
            for row in users:
                if str(row.get("id") or "") == str(user_id):
                    user = {
                        "id": row.get("id"),
                        "firstName": row.get("firstName"),
                        "lastName": row.get("lastName"),
                        "email": row.get("email"),
                        "userType": row.get("userType"),
                        "isActive": not bool(row.get("inactive")),
                    }
                    break
        if not user:
            return {}
        return {
            "id": user.get("id") or str(user_id),
            "name": " ".join(
                part for part in [user.get("firstName"), user.get("lastName")] if part
            ).strip()
            or "Unknown",
            "email": user.get("email"),
            "user_type": user.get("userType"),
            "is_active": user.get("isActive"),
        }

    def get_customer_summary(self, customer_id: int) -> dict[str, Any]:
        try:
            xml = self.client.customers.list()
        except Exception as exc:
            return {"id": str(customer_id), "error": str(exc)}

        needle = str(customer_id)
        customer = None
        for node in xml.findall(".//customer"):
            if (node.findtext("customerId") or "") == needle:
                customer = node
                break
        if customer is None:
            return {}

        return {
            "id": customer.findtext("customerId") or needle,
            "name": customer.findtext("customerName") or "Customer",
            "type": customer.findtext("customerType"),
            "inactive": customer.findtext("inactive") == "1",
        }

    def bluefolder_status(self) -> dict[str, Any]:
        """Small connectivity/config status report for admin troubleshooting."""
        try:
            techs = self.list_active_techs()
            return {
                "ok": True,
                "base_url": settings.bluefolder_base_url,
                "host_header": settings.bluefolder_host_header,
                "verify_ssl": settings.bluefolder_verify_ssl,
                "active_tech_count": len(techs),
            }
        except Exception as exc:
            return {
                "ok": False,
                "base_url": settings.bluefolder_base_url,
                "host_header": settings.bluefolder_host_header,
                "verify_ssl": settings.bluefolder_verify_ssl,
                "error": str(exc),
            }

    def resolve_tech_id(self, discord_user_id: int, candidate_names: list[str] | None = None) -> int | None:
        mapped = settings.parsed_discord_tech_map.get(str(discord_user_id))
        if mapped:
            return mapped

        candidates = [self._clean_text(name) for name in (candidate_names or [])]
        candidate_set = {name.casefold() for name in candidates if name}
        if not candidate_set:
            return None

        matches = [
            tech for tech in self.list_active_techs() if tech.get("name", "").casefold() in candidate_set
        ]
        if len(matches) == 1:
            return matches[0]["id"]
        return None

    def get_assignments_for_user_today(self, user_id: int) -> list[dict[str, Any]]:
        return self.get_assignments_for_user_day(user_id, day=date.today())

    def get_assignments_for_user_day(self, user_id: int, day: date) -> list[dict[str, Any]]:
        cache_key = ("day", user_id, day.isoformat())
        cached = self._get_cached_assignments(cache_key)
        if cached is not None:
            return cached
        start_date = f"{day.strftime('%Y.%m.%d')} 12:00 AM"
        end_date = f"{day.strftime('%Y.%m.%d')} 11:59 PM"
        assignments = self.client.assignments.list_for_user_range(
            user_id,
            start_date,
            end_date,
            date_range_type="scheduled",
        )
        enriched = self._enrich_assignments(assignments)
        self._set_cached_assignments(cache_key, enriched)
        return enriched

    def get_assignments_for_user_window(
        self,
        user_id: int,
        *,
        start_day: date,
        end_day: date,
    ) -> list[dict[str, Any]]:
        cache_key = ("window", user_id, start_day.isoformat(), end_day.isoformat())
        cached = self._get_cached_assignments(cache_key)
        if cached is not None:
            return cached
        start_date = f"{start_day.strftime('%Y.%m.%d')} 12:00 AM"
        end_date = f"{end_day.strftime('%Y.%m.%d')} 11:59 PM"
        assignments = self.client.assignments.list_for_user_range(
            user_id,
            start_date,
            end_date,
            date_range_type="scheduled",
        )
        enriched = self._enrich_assignments(assignments)
        self._set_cached_assignments(cache_key, enriched)
        return enriched

    def _enrich_assignments(self, assignments: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
                    "start_display": self._format_dt(a.get("start")),
                    "end_display": self._format_dt(a.get("end")),
                    "is_complete": a.get("isComplete"),
                }
            )
        return sorted(results, key=lambda item: item.get("start") or "")

    def get_assignment_for_sr_window(
        self,
        user_id: int,
        sr_id: int,
        *,
        start_day: date,
        end_day: date,
    ) -> dict[str, Any] | None:
        target = str(sr_id)
        for assignment in self.get_assignments_for_user_window(
            user_id,
            start_day=start_day,
            end_day=end_day,
        ):
            if str(assignment.get("service_request_id") or "") == target:
                return assignment
        return None

    def get_assignment_for_sr_in_workflow_window(self, user_id: int, sr_id: int) -> dict[str, Any] | None:
        today = date.today()
        start_day = today.fromordinal(
            today.toordinal() - max(int(settings.workflow_assignment_lookup_days_before), 0)
        )
        end_day = today.fromordinal(
            today.toordinal() + max(int(settings.workflow_assignment_lookup_days_after), 0)
        )
        return self.get_assignment_for_sr_window(
            user_id,
            sr_id,
            start_day=start_day,
            end_day=end_day,
        )

    def get_dispatch_loads_for_day(self, day: date, limit: int = 10) -> list[dict[str, Any]]:
        """Summarize assignment counts for active techs on a given day."""
        loads: list[dict[str, Any]] = []
        for tech in self.list_active_techs():
            try:
                assignments = self.get_assignments_for_user_day(tech["id"], day)
            except Exception:
                assignments = []
            loads.append(
                {
                    "tech_id": tech["id"],
                    "tech_name": tech["name"],
                    "assignment_count": len(assignments),
                    "first_start": assignments[0].get("start_display") if assignments else None,
                }
            )
        loads.sort(key=lambda item: (-item["assignment_count"], item["tech_name"].casefold()))
        return loads[:limit]

    def find_sr_assignment_window(self, sr_id: int, *, start_day: date, end_day: date) -> list[dict[str, Any]]:
        """Find which active techs are assigned to a given SR in a date window."""
        matches: list[dict[str, Any]] = []
        target = str(sr_id)
        for tech in self.list_active_techs():
            try:
                assignments = self.get_assignments_for_user_window(
                    tech["id"],
                    start_day=start_day,
                    end_day=end_day,
                )
            except Exception:
                continue
            for assignment in assignments:
                if str(assignment.get("service_request_id") or "") != target:
                    continue
                matches.append(
                    {
                        "tech_id": tech["id"],
                        "tech_name": tech["name"],
                        "start": assignment.get("start_display") or assignment.get("start"),
                        "end": assignment.get("end_display") or assignment.get("end"),
                        "subject": assignment.get("subject"),
                    }
                )
        return matches

    def get_customer_contacts(
        self, customer_id: str | None, location_id: str | None = None
    ) -> list[dict[str, Any]]:
        cid = self._safe_int(customer_id)
        if not cid:
            return []
        try:
            contacts = self.client.customer_contacts.list_for_customer(cid)
        except Exception:
            return []

        filtered = []
        for contact in contacts:
            if location_id and contact.get("locationId") not in (None, "", str(location_id)):
                continue
            name = " ".join(
                part for part in [contact.get("firstName"), contact.get("lastName")] if part
            ).strip()
            filtered.append(
                {
                    "name": name or "Unknown",
                    "title": contact.get("title"),
                    "phone": contact.get("phone"),
                    "email": contact.get("email"),
                    "is_primary": bool(contact.get("isPrimary")),
                }
            )

        filtered.sort(key=lambda item: (not item["is_primary"], item["name"].casefold()))
        return filtered

    def get_service_request(self, sr_id: int) -> dict[str, Any]:
        try:
            sr_xml = self.client.service_requests.get_by_id(sr_id)
        except Exception as exc:
            return {
                "id": str(sr_id),
                "error": str(exc),
            }
        sr = sr_xml.find(".//serviceRequest")
        if sr is None:
            return {}

        customer_id = sr.findtext("customerId")
        location_id = sr.findtext("customerLocationId")
        location = self._location_dict(customer_id, location_id) or {
            "name": sr.findtext("customerLocationName"),
            "street": sr.findtext("customerLocationStreetAddress"),
            "city": sr.findtext("customerLocationCity"),
            "state": sr.findtext("customerLocationState"),
            "postal_code": sr.findtext("customerLocationPostalCode"),
            "notes": sr.findtext("customerLocationNotes"),
        }
        customer = self._customer_dict(customer_id) or {}
        customer = {
            "id": customer.get("id") or customer_id,
            "name": customer.get("name") or sr.findtext("customerName"),
            "phone": customer.get("phone") or sr.findtext("customerContactPhone"),
            "email": customer.get("email") or sr.findtext("customerContactEmail"),
        }
        fallback_name = (
            sr.findtext("customerContactName")
            or " ".join(
                part
                for part in [
                    sr.findtext("customerContactFirstName"),
                    sr.findtext("customerContactLastName"),
                ]
                if part
            ).strip()
        )
        contacts: list[dict[str, Any]] = []
        if fallback_name or sr.findtext("customerContactPhone") or sr.findtext("customerContactEmail"):
            contacts = [
                {
                    "name": fallback_name or "Primary Contact",
                    "title": None,
                    "phone": sr.findtext("customerContactPhone"),
                    "email": sr.findtext("customerContactEmail"),
                    "is_primary": True,
                }
            ]
        elif customer_id:
            contacts = self.get_customer_contacts(customer_id, location_id)

        address = None
        if location:
            parts = [
                location.get("street"),
                location.get("city"),
                location.get("state"),
                location.get("postal_code"),
            ]
            address = ", ".join([part for part in parts if part])

        return {
            "id": sr.findtext("id") or str(sr_id),
            "subject": sr.findtext("description") or sr.findtext("subject") or "Service Request",
            "status": sr.findtext("status"),
            "priority": sr.findtext("priority"),
            "customer_id": customer_id,
            "location_id": location_id,
            "customer_name": (customer or {}).get("name"),
            "customer_phone": (customer or {}).get("phone"),
            "customer_email": (customer or {}).get("email"),
            "contacts": contacts,
            "site_name": (location or {}).get("name"),
            "site_notes": (location or {}).get("notes"),
            "address": address,
            "equipment": self._equipment_from_sr(sr),
        }

    def _get_service_request_xml(self, sr_id: int) -> Any | None:
        try:
            sr_xml = self.client.service_requests.get_by_id(sr_id)
        except Exception:
            return None
        return sr_xml.find(".//serviceRequest")

    def get_service_request_notes(self, sr_id: int, limit: int = 5) -> list[dict[str, Any]]:
        try:
            hist_xml = self.client.service_requests.get_history(sr_id)
        except Exception:
            return []

        notes: list[dict[str, Any]] = []
        for entry in hist_xml.findall(".//serviceRequestHistory"):
            notes.append(
                {
                    "dateCreated": entry.findtext("entryDate"),
                    "author": entry.findtext("userName"),
                    "text": self._clean_html_text(
                        entry.findtext("comment") or entry.findtext("description")
                    ),
                    "entryType": entry.findtext("entryType"),
                }
            )
        notes = [note for note in notes if note.get("text")]
        notes = sorted(notes, key=lambda item: item.get("dateCreated") or "", reverse=True)
        return notes[:limit]

    def get_service_request_history(self, sr_id: int, limit: int = 12) -> list[dict[str, Any]]:
        """Return a broader history feed than `/notes`."""
        return self.get_service_request_notes(sr_id, limit=limit)

    def get_service_request_attachments(self, sr_id: int, limit: int = 10) -> list[dict[str, Any]]:
        try:
            rows = self.client.attachments.list_for_service_request(sr_id)
        except Exception:
            return []
        rows = sorted(
            rows,
            key=lambda item: item.get("postedOn") or item.get("dateCreated") or "",
            reverse=True,
        )
        return rows[:limit]

    def get_service_request_equipment(self, sr_id: int, limit: int = 10) -> list[dict[str, Any]]:
        item = self.get_service_request(sr_id)
        if item.get("equipment"):
            return item["equipment"][:limit]
        customer_id = self._safe_int(item.get("customer_id"))
        if not customer_id:
            return []
        try:
            rows = self.client.equipment.list_for_customer(customer_id)
        except Exception:
            return []

        location_id = str(item.get("location_id") or "")
        if location_id:
            filtered = [row for row in rows if str(row.get("locationId") or "") == location_id]
            if filtered:
                rows = filtered
        return rows[:limit]

    def get_service_request_materials(self, sr_id: int, limit: int = 10) -> list[dict[str, Any]]:
        sr = self._get_service_request_xml(sr_id)
        if sr is None:
            return []
        rows = self._materials_from_sr(sr)
        return rows[:limit]

    def get_service_request_labor(self, sr_id: int, limit: int = 10) -> list[dict[str, Any]]:
        sr = self._get_service_request_xml(sr_id)
        if sr is None:
            return []
        rows = self._labor_from_sr(sr)
        rows = sorted(rows, key=lambda item: item.get("date") or "", reverse=True)
        return rows[:limit]

    def search_recent_service_requests(
        self,
        query: str,
        *,
        field: str,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        cleaned = self._clean_text(query)
        if not cleaned:
            return []

        if field == "customer":
            try:
                xml = self.client.customers.list()
            except Exception:
                return []
            needle = cleaned.casefold()
            matches: list[dict[str, Any]] = []
            for customer in xml.findall(".//customer"):
                name = customer.findtext("customerName") or ""
                if needle not in name.casefold():
                    continue
                matches.append(
                    {
                        "id": customer.findtext("customerId"),
                        "subject": name,
                        "address": "",
                        "start": None,
                        "end": None,
                    }
                )
            matches.sort(key=lambda item: (item.get("subject") or "").casefold())
            return matches[:limit]

        # BlueFolder does not expose a workable global location search on this tenant.
        return []

    def add_service_request_note(
        self,
        sr_id: int,
        text: str,
        *,
        user_id: int | None = None,
        visible_to_customer: bool = False,
    ) -> dict[str, Any]:
        cleaned = self._clean_text(text)
        if not cleaned:
            return {"ok": False, "error": "Note text is empty."}
        effective_user_id = user_id or settings.bluefolder_comment_user_id
        if not effective_user_id:
            return {
                "ok": False,
                "error": "No BlueFolder user ID is available for this note. Map your Discord user in DISCORD_TECH_MAP or set BLUEFOLDER_COMMENT_USER_ID.",
            }
        try:
            response = self.client.service_requests.add_comment(
                sr_id,
                cleaned,
                user_id=effective_user_id,
                comment_is_public=visible_to_customer,
            )
            if response.attrib.get("status") == "fail":
                error = response.findtext(".//error") or "BlueFolder rejected the note."
                return {"ok": False, "error": error}
            return {"ok": True}
        except Exception as exc:
            return {"ok": False, "error": str(exc)}

    @classmethod
    def _extract_labeled_sections(cls, text: str | None) -> dict[str, str]:
        if not text:
            return {}
        normalized = text.replace("\r\n", "\n").replace("\r", "\n")
        labels = {
            "cx complaint": "complaint",
            "customer complaint": "complaint",
            "diagnosis": "diagnosis",
            "work performed": "work_performed",
            "parts needed": "parts_needed",
            "parts used": "parts_used",
        }
        found: dict[str, str] = {}
        current_key: str | None = None
        chunks: list[str] = []

        def flush() -> None:
            nonlocal current_key, chunks
            if current_key and chunks and current_key not in found:
                value = cls._clean_text(" ".join(chunks))
                if value:
                    found[current_key] = value
            current_key = None
            chunks = []

        for raw_line in normalized.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            lowered = line.casefold()
            matched_key = None
            rest = ""
            for label, key in labels.items():
                prefix = f"{label} -"
                if lowered.startswith(prefix):
                    matched_key = key
                    rest = line[len(prefix):].strip()
                    break
                prefix = f"{label}:"
                if lowered.startswith(prefix):
                    matched_key = key
                    rest = line[len(prefix):].strip()
                    break
            if matched_key:
                flush()
                current_key = matched_key
                if rest:
                    chunks.append(rest)
                continue
            if current_key:
                chunks.append(line)
        flush()
        return found

    def build_troubleshooting_summary(self, sr_id: int) -> dict[str, Any]:
        item = self.get_service_request(sr_id)
        if item.get("error"):
            return item
        if not item:
            return {"error": "Service request not found."}

        labor_rows = self.get_service_request_labor(sr_id, limit=3)
        notes = self.get_service_request_notes(sr_id, limit=8)

        sections: dict[str, str] = {}
        source_text = None
        for row in labor_rows:
            description = row.get("description")
            extracted = self._extract_labeled_sections(description)
            if extracted:
                sections = extracted
                source_text = description
                break

        if not sections:
            for note in notes:
                extracted = self._extract_labeled_sections(note.get("text"))
                if extracted:
                    sections = extracted
                    source_text = note.get("text")
                    break

        summary = {
            "sr_id": item["id"],
            "subject": item.get("subject"),
            "customer_name": item.get("customer_name"),
            "address": item.get("address"),
            "sections": sections,
            "recent_notes": notes[:3],
            "latest_labor": labor_rows[:2],
            "source_text": source_text,
        }
        return summary

    def log_contact_issue(
        self,
        sr_id: int,
        *,
        user_id: int,
        issue_type: str,
        details: str | None = None,
    ) -> dict[str, Any]:
        assignment = self.get_assignment_for_sr_in_workflow_window(user_id, sr_id)
        if not assignment:
            return {"ok": False, "error": "No assignment for this SR is mapped to you in the configured workflow window."}

        item = self.get_service_request(sr_id)
        now = datetime.now().replace(second=0, microsecond=0)
        contact_bits: list[str] = []
        if item.get("customer_phone"):
            contact_bits.append(f"phone={item['customer_phone']}")
        if item.get("customer_email"):
            contact_bits.append(f"email={item['customer_email']}")
        contact_text = f" Contact info: {', '.join(contact_bits)}." if contact_bits else ""
        detail_text = f" Details: {details.strip()}." if details and details.strip() else ""

        if issue_type == "no_answer":
            text = (
                f"Customer no-answer at {now.strftime('%I:%M %p').lstrip('0')}."
                f"{contact_text}{detail_text}"
            )
        elif issue_type == "not_home":
            text = (
                f"Customer not home at arrival at {now.strftime('%I:%M %p').lstrip('0')}."
                f"{contact_text}{detail_text}"
            )
        else:
            text = (
                f"Access issue reported at {now.strftime('%I:%M %p').lstrip('0')}."
                f"{contact_text}{detail_text}"
            )

        result = self.add_service_request_note(
            sr_id,
            text,
            user_id=user_id,
            visible_to_customer=False,
        )
        if not result.get("ok"):
            return result
        return {
            "ok": True,
            "logged_at": now.isoformat(timespec="minutes"),
            "note_text": text,
            "issue_type": issue_type,
            "customer_name": item.get("customer_name"),
            "address": item.get("address"),
            "customer_phone": item.get("customer_phone"),
            "customer_email": item.get("customer_email"),
        }

    def log_parts_issue(
        self,
        sr_id: int,
        *,
        user_id: int,
        issue_type: str,
        details: str,
    ) -> dict[str, Any]:
        assignment = self.get_assignment_for_sr_in_workflow_window(user_id, sr_id)
        if not assignment:
            return {"ok": False, "error": "No assignment for this SR is mapped to you in the configured workflow window."}

        item = self.get_service_request(sr_id)
        now = datetime.now().replace(second=0, microsecond=0)
        detail_text = self._clean_text(details)
        if not detail_text:
            return {"ok": False, "error": "Part details are required."}

        if issue_type == "missing_part":
            text = (
                f"Missing part reported at {now.strftime('%I:%M %p').lstrip('0')}. "
                f"Details: {detail_text}."
            )
        else:
            text = (
                f"Damaged part reported at {now.strftime('%I:%M %p').lstrip('0')}. "
                f"Details: {detail_text}."
            )

        result = self.add_service_request_note(
            sr_id,
            text,
            user_id=user_id,
            visible_to_customer=False,
        )
        if not result.get("ok"):
            return result
        return {
            "ok": True,
            "logged_at": now.isoformat(timespec="minutes"),
            "note_text": text,
            "issue_type": issue_type,
            "customer_name": item.get("customer_name"),
            "address": item.get("address"),
        }

    def _bluefolder_ok(self, response: Any) -> dict[str, Any]:
        if response is None:
            return {"ok": False, "error": "Empty BlueFolder response."}
        if getattr(response, "attrib", {}).get("status") == "fail":
            error = response.findtext(".//error") or "BlueFolder rejected the request."
            return {"ok": False, "error": error}
        return {"ok": True}

    def _update_assignment_comment(self, assignment_id: int, comment: str) -> dict[str, Any]:
        try:
            response = self.client.service_requests.edit_assignment(
                assignment_id,
                assignmentComment=comment,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        result = self._bluefolder_ok(response)
        if result.get("ok"):
            self._clear_assignment_cache()
        return result

    def _complete_assignment(self, assignment_id: int, comment: str | None = None) -> dict[str, Any]:
        try:
            response = self.client.service_requests.complete_assignment(
                assignment_id,
                comment=comment,
            )
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        result = self._bluefolder_ok(response)
        if result.get("ok"):
            self._clear_assignment_cache()
        return result

    def _workflow_targets(self) -> list[str]:
        targets: list[str] = []
        if settings.workflow_write_assignment:
            targets.append("assignment")
        if settings.workflow_write_sr_note:
            targets.append("sr_note")
        return targets

    def _write_workflow_update(
        self,
        sr_id: int,
        *,
        user_id: int,
        assignment_id: int,
        text: str,
        complete_assignment: bool = False,
    ) -> dict[str, Any]:
        targets = self._workflow_targets()
        if not targets:
            return {"ok": False, "error": "Workflow writes are disabled by configuration."}

        if settings.workflow_write_assignment:
            if complete_assignment:
                result = self._complete_assignment(assignment_id, comment=text)
            else:
                result = self._update_assignment_comment(assignment_id, text)
            if not result.get("ok"):
                return result

        if settings.workflow_write_sr_note:
            result = self.add_service_request_note(
                sr_id,
                text,
                user_id=user_id,
                visible_to_customer=False,
            )
            if not result.get("ok"):
                return result

        return {"ok": True, "stored_as": " + ".join(targets)}

    def mark_eta(
        self,
        sr_id: int,
        *,
        user_id: int,
        minutes: int,
    ) -> dict[str, Any]:
        assignment = self.get_assignment_for_sr_in_workflow_window(user_id, sr_id)
        if not assignment:
            return {"ok": False, "error": "No assignment for this SR is mapped to you in the configured workflow window."}
        eta_at = datetime.now().replace(second=0, microsecond=0)
        eta_msg = f"ETA update: arriving in {minutes} minutes."
        write_result = self._write_workflow_update(
            sr_id,
            user_id=user_id,
            assignment_id=int(assignment["assignment_id"]),
            text=eta_msg,
        )
        if not write_result.get("ok"):
            return write_result
        return {
            "ok": True,
            "assignment_id": assignment["assignment_id"],
            "stored_as": write_result.get("stored_as"),
            "eta_minutes": minutes,
            "recorded_at": eta_at.isoformat(timespec="minutes"),
        }

    def mark_enroute(self, sr_id: int, *, user_id: int) -> dict[str, Any]:
        assignment = self.get_assignment_for_sr_in_workflow_window(user_id, sr_id)
        if not assignment:
            return {"ok": False, "error": "No assignment for this SR is mapped to you in the configured workflow window."}
        now = datetime.now().replace(second=0, microsecond=0)
        text = f"Technician en route at {now.strftime('%I:%M %p').lstrip('0')}."
        write_result = self._write_workflow_update(
            sr_id,
            user_id=user_id,
            assignment_id=int(assignment["assignment_id"]),
            text=text,
        )
        if not write_result.get("ok"):
            return write_result
        return {
            "ok": True,
            "assignment_id": assignment["assignment_id"],
            "stored_as": write_result.get("stored_as"),
            "timestamp": now.isoformat(timespec="minutes"),
        }

    def mark_start(self, sr_id: int, *, user_id: int) -> dict[str, Any]:
        assignment = self.get_assignment_for_sr_in_workflow_window(user_id, sr_id)
        if not assignment:
            return {"ok": False, "error": "No assignment for this SR is mapped to you in the configured workflow window."}
        now = datetime.now().replace(second=0, microsecond=0)
        text = f"Technician started work at {now.strftime('%I:%M %p').lstrip('0')}."
        write_result = self._write_workflow_update(
            sr_id,
            user_id=user_id,
            assignment_id=int(assignment["assignment_id"]),
            text=text,
        )
        if not write_result.get("ok"):
            return write_result
        return {
            "ok": True,
            "assignment_id": assignment["assignment_id"],
            "stored_as": write_result.get("stored_as"),
            "started_at": now.isoformat(timespec="minutes"),
        }

    def mark_complete(self, sr_id: int, *, user_id: int) -> dict[str, Any]:
        assignment = self.get_assignment_for_sr_in_workflow_window(user_id, sr_id)
        if not assignment:
            return {"ok": False, "error": "No assignment for this SR is mapped to you in the configured workflow window."}
        now = datetime.now().replace(second=0, microsecond=0)
        text = f"Technician marked assignment complete at {now.strftime('%I:%M %p').lstrip('0')}."
        write_result = self._write_workflow_update(
            sr_id,
            user_id=user_id,
            assignment_id=int(assignment["assignment_id"]),
            text=text,
            complete_assignment=True,
        )
        if not write_result.get("ok"):
            return write_result
        return {
            "ok": True,
            "assignment_id": assignment["assignment_id"],
            "stored_as": write_result.get("stored_as"),
            "completed_at": now.isoformat(timespec="minutes"),
        }

    def build_waiver_link(self, sr_id: int) -> dict[str, Any]:
        item = self.get_service_request(sr_id)
        if not item:
            return {"error": "Service request not found."}
        if item.get("error"):
            return item
        if not settings.waiver_base_url:
            return {"error": "WAIVER_BASE_URL is not configured."}

        customer_name = item.get("customer_name") or "Customer"
        first_name, last_name = self._split_name_parts(customer_name)
        query = urlencode(
            {
                settings.waiver_sr_param: item["id"],
                settings.waiver_name_param: customer_name,
                settings.waiver_first_name_param: first_name,
                settings.waiver_last_name_param: last_name,
            }
        )
        return {
            "sr_id": item["id"],
            "customer_name": customer_name,
            "customer_first_name": first_name,
            "customer_last_name": last_name,
            "url": f"{settings.waiver_base_url}?{query}",
        }
