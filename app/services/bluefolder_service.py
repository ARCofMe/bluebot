"""BlueFolder service helpers for the Discord bot."""

from __future__ import annotations

import html
import os
import re
import sys
from datetime import datetime
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

        from bluefolder_api.client import BlueFolderClient  # type: ignore

        client_kwargs = {}
        if settings.bluefolder_base_url:
            client_kwargs["base_url"] = settings.bluefolder_base_url
        self.client = BlueFolderClient(**client_kwargs)

    def _ensure_runtime_dependencies(self) -> None:
        """Fail fast when the HTTP client dependency is missing."""
        try:
            import requests  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "Missing Python dependency 'requests'. Run `python -m pip install -r requirements.txt` in bluebot-discord-extension."
            ) from exc

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
                    "start_display": self._format_dt(a.get("start")),
                    "end_display": self._format_dt(a.get("end")),
                    "is_complete": a.get("isComplete"),
                }
            )
        return sorted(results, key=lambda item: item.get("start") or "")

    def get_dispatch_loads_today(self, limit: int = 10) -> list[dict[str, Any]]:
        """Summarize today's assignment counts for active techs."""
        loads: list[dict[str, Any]] = []
        for tech in self.list_active_techs():
            try:
                assignments = self.get_assignments_for_user_today(tech["id"])
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

    def find_sr_assignment_today(self, sr_id: int) -> list[dict[str, Any]]:
        """Find which active techs are assigned to a given SR today."""
        matches: list[dict[str, Any]] = []
        target = str(sr_id)
        for tech in self.list_active_techs():
            try:
                assignments = self.get_assignments_for_user_today(tech["id"])
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
        try:
            rows = self.client.materials.list_for_service_request(sr_id)
        except Exception:
            return []
        return rows[:limit]

    def get_service_request_labor(self, sr_id: int, limit: int = 10) -> list[dict[str, Any]]:
        try:
            rows = self.client.labor.list_for_service_request(sr_id)
        except Exception:
            return []
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
