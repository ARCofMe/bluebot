"""Integration helpers that wrap the BlueFolder API client."""

import logging
from datetime import date
from bluefolder_api.client import BlueFolderClient
from app.utils.cache_manager import CacheManager

logger = logging.getLogger(__name__)


class BlueFolderIntegration:
    """Integration layer between BlueBot and the BlueFolder API."""

    def __init__(self):
        """Instantiate the underlying BlueFolder API client."""
        self.client = BlueFolderClient()

    def get_user_assignments_today(self, user_id: int):
        """Retrieve and enrich today's assignments for a given BlueFolder user."""
        today = date.today().strftime("%Y.%m.%d")
        start_date = f"{today} 12:00 AM"
        end_date = f"{today} 11:59 PM"

        logger.info(f"Fetching BlueFolder assignments {start_date} → {end_date}")

        sr_cache = CacheManager("service_requests", ttl_minutes=60)
        loc_cache = CacheManager("locations", ttl_minutes=120)

        assignments = self.client.assignments.list_for_user_range(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            date_range_type="scheduled",
        )

        enriched = []
        for a in assignments:
            sr_id = a.get("serviceRequestId")
            if not sr_id:
                continue

            # --- 1️⃣ Service Request (cache-aware)
            sr_data = sr_cache.get(sr_id)
            if not sr_data:
                sr_xml = self.client.service_requests.get_by_id(sr_id)
                sr = sr_xml.find(".//serviceRequest")
                if sr is None:
                    continue

                sr_data = {
                    "customerId": sr.findtext("customerId"),
                    "locationId": sr.findtext("customerLocationId"),
                    "subject": (
                        sr.findtext("description")
                        or sr.findtext("subject")
                        or sr.findtext(".//subject")
                        or sr.findtext(".//title")
                        or "Unlabeled Service Request"
                    ),
                }
                sr_cache.set(sr_id, sr_data)

            customer_id = sr_data.get("customerId")
            location_id = sr_data.get("locationId")

            # --- 2️⃣ Location (cache-aware)
            loc_key = f"{customer_id}:{location_id}"
            loc_data = loc_cache.get(loc_key)

            if not loc_data and customer_id and location_id:
                loc_xml = self.client.customers.get_location_by_id(customer_id, location_id)
                loc = loc_xml.find(".//customerLocation")
                if loc is not None:
                    loc_data = {
                        "address": loc.findtext("addressStreet"),
                        "city": loc.findtext("addressCity"),
                        "state": loc.findtext("addressState"),
                        "zip": loc.findtext("addressPostalCode"),
                    }
                    loc_cache.set(loc_key, loc_data)

            # --- 3️⃣ Combine enriched record
            enriched.append(
                {
                    "assignmentId": a.get("assignmentId"),
                    "serviceRequestId": sr_id,
                    "subject": sr_data.get("subject"),
                    "address": loc_data.get("address") if loc_data else None,
                    "city": loc_data.get("city") if loc_data else None,
                    "state": loc_data.get("state") if loc_data else None,
                    "zip": loc_data.get("zip") if loc_data else None,
                    "start": a.get("start"),
                    "end": a.get("end"),
                    "isComplete": a.get("isComplete"),
                }
            )

        logger.info(f"[CACHE] saved: {len(sr_cache.data)} SRs, {len(loc_cache.data)} locations")
        return enriched
