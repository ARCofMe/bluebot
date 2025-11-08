from fastapi import APIRouter, Query, Response
from app.integrations.bluefolder_integration import BlueFolderIntegration
from app.utils.cache_manager import CacheManager
from teams_notifier_extension.notifier.manager import TeamsNotifier
import logging
from datetime import datetime

router = APIRouter(prefix="/api/bluefolder/assignments", tags=["BlueFolder"])
logger = logging.getLogger(__name__)


@router.get("/today/{user_id}")
async def get_today_assignments(
    user_id: int,
    details: bool = Query(
        False, description="Include full service request details and locations"
    ),
    cached: bool = Query(True, description="Use cached data if available"),
    summary: bool = Query(False, description="Return text-based summary lines"),
    format: str = Query(
        "json", description="Response format: 'json' (default) or 'text'"
    ),
    send_to_teams: bool = Query(
        False, description="Send the plain-text summary to Teams webhook"
    ),
):
    """
    Retrieve today's BlueFolder assignments for a specific user.

    Query Parameters:
    - `details`: include enriched SR and customer location data
    - `cached`: use cached results if available (default: True)
    - `summary`: include readable summary lines (for Teams, DM, etc.)
    - `format`: 'json' or 'text'
    - `send_to_teams`: if true, automatically send the summary to your Teams channel
    """
    logger.info(
        f"[API] Assignments → user={user_id}, details={details}, cached={cached}, "
        f"summary={summary}, format={format}, send_to_teams={send_to_teams}"
    )

    bf = BlueFolderIntegration()

    # Optional cache bypass
    if not cached:
        logger.info("[CACHE] Forced refresh: clearing assignment cache.")
        CacheManager("service_requests").clear()
        CacheManager("locations").clear()

    # Retrieve assignments
    if details:
        assignments = bf.get_user_assignments_today(user_id)
    else:
        today = datetime.now().strftime("%Y.%m.%d")
        start_date = f"{today} 12:00 AM"
        end_date = f"{today} 11:59 PM"
        assignments = bf.client.assignments.list_for_user_range(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
            date_range_type="scheduled",
        )

    # --- Build summary lines ---
    lines = []
    for a in assignments:
        start = a.get("start")
        end = a.get("end")

        # Time formatting
        try:
            if start and end:
                start_str = datetime.fromisoformat(start).strftime("%H:%M")
                end_str = datetime.fromisoformat(end).strftime("%H:%M")
                time_str = f"[{start_str}–{end_str}]"
            else:
                time_str = "[time unknown]"
        except Exception:
            time_str = "[time unknown]"

        subject = a.get("subject") or "No subject"
        city = a.get("city") or ""
        state = a.get("state") or ""
        loc_str = f"({city}, {state})" if city or state else ""
        sr_str = f"SR-{a.get('serviceRequestId', '?')}"
        lines.append(f"{time_str} {sr_str} – {subject} {loc_str}".strip())

    text_summary = (
        f"📋 **Assignments for user {user_id}** ({len(assignments)} total):\n"
        + "\n".join(lines)
    )

    # --- Optional: Send to Teams ---
    if send_to_teams:
        try:
            notifier = TeamsNotifier()
            context = {
                "title": f"Assignments for {user_id}",
                "summary": f"{len(assignments)} total assignments.",
                "details": text_summary,
            }
            success = notifier.send_notification(context)
            if success:
                logger.info("[TEAMS] Successfully sent summary to Teams.")
            else:
                logger.error("[TEAMS] Failed to send summary to Teams.")
        except Exception as e:
            logger.exception(f"[TEAMS] Exception while sending Teams message: {e}")

    # --- TEXT MODE OUTPUT ---
    if format == "text":
        return Response(content=text_summary, media_type="text/plain")

    # --- JSON OUTPUT ---
    response = {
        "user_id": user_id,
        "count": len(assignments),
        "assignments": assignments,
    }
    if summary or format == "text":
        response["summary_lines"] = lines

    return response
