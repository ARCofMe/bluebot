"""Discord client and slash commands."""

from __future__ import annotations

from datetime import date, timedelta
from difflib import SequenceMatcher
import json
import re

import discord
from discord import app_commands
from discord.ext import commands

from app.core.config import export_output_path, settings
from app.services.bluefolder_service import BlueFolderService


class PartsCannonDiscord(commands.Bot):
    """Discord bot wired to BlueFolder helpers."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)
        self.bluefolder = BlueFolderService()

    async def setup_hook(self) -> None:
        if settings.discord_guild_id:
            guild = discord.Object(id=settings.discord_guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()


bot = PartsCannonDiscord()
_DISCORD_MESSAGE_LIMIT = 2000


def _my_tech_id(interaction: discord.Interaction) -> int | None:
    names = [
        getattr(interaction.user, "display_name", None),
        getattr(interaction.user, "global_name", None),
        getattr(interaction.user, "name", None),
    ]
    return bot.bluefolder.resolve_tech_id(
        interaction.user.id,
        [name for name in names if name],
    )


def _my_tech_help() -> str:
    return (
        "Your Discord user is not mapped to a BlueFolder tech yet. "
        "Set `DISCORD_TECH_MAP` in `.env` or use `/assignments_today tech_id:<id>`."
    )


def _parse_iso_date(raw: str) -> date | None:
    try:
        return date.fromisoformat(raw)
    except Exception:
        return None


def _normalize_name(raw: str | None) -> str:
    text = " ".join(str(raw or "").split()).strip().casefold()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    return text


def _member_name_candidates_from_record(member: dict[str, object]) -> list[str]:
    candidates: list[str] = []
    for raw in [member.get("display_name"), member.get("global_name"), member.get("username")]:
        normalized = _normalize_name(str(raw or ""))
        if normalized and normalized not in candidates:
            candidates.append(normalized)
    return candidates


def _chunk_lines(lines: list[str], *, limit: int = _DISCORD_MESSAGE_LIMIT) -> list[str]:
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + (1 if current else 0)
        if current and current_len + line_len > limit:
            chunks.append("\n".join(current))
            current = [line]
            current_len = len(line)
            continue
        current.append(line)
        current_len += line_len

    if current:
        chunks.append("\n".join(current))
    return chunks


def _help_sections() -> list[tuple[str, list[str]]]:
    sections = {
        "General": [
            "/bf_status - BlueFolder connectivity/config status",
            "/help - show this command list",
            "/ping - verify bot connectivity",
            "/waiver sr_id - generate the prefilled waiver link",
        ],
        "Dispatch": [
            "/next_openings - show which techs are lightest today",
            "/sr_brief sr_id - compact dispatch summary for a service request",
            "/today_board - today's tech load snapshot for dispatch",
        ],
        "Parts": [
            "/parts_notes sr_id - recent parts-related notes for a service request",
            "/parts_brief sr_id - compact parts-facing summary for a service request",
        ],
        "Mapping And Admin": [
            "/export_member_map scope - export Discord user ids/names for env mapping",
            "/lookup_member user - inspect one Discord member's BlueFolder mapping state",
            "/mapping_drift scope - audit role and mapping drift across members",
            "/role_audit scope - summarize configured Discord role coverage",
            "/suggest_tech_map scope - suggest DISCORD_TECH_MAP from Discord names vs BlueFolder techs",
            "/tech_map_status scope - audit mapping coverage for guild/channel members",
            "/who_am_i_mapped_to - show your Discord to BlueFolder tech mapping status",
        ],
        "Tech Schedules": [
            "/assignments_today tech_id - today's assignments for a tech",
            "/my_day date - show your assignments for a specific YYYY-MM-DD date",
            "/my_jobs - today's assignments for your mapped tech",
            "/my_next_packet - compact packet for your next assignment",
            "/my_status - show your mapping, today's job count, and next assignment",
            "/my_week - show your assignment counts for the next 7 days",
            "/next_job - your next scheduled assignment today",
            "/tech_day tech_id date - assignments for one tech on a specific day",
            "/tech_loads - today's assignment counts by tech",
            "/techs - list active BlueFolder technicians",
            "/who_has_sr sr_id - find who has a service request in the next 14 days",
        ],
        "Service Requests": [
            "/attachments sr_id - recent service request attachments",
            "/customer sr_id - customer and contact details",
            "/equipment sr_id - customer equipment for the job site",
            "/find_sr text - search recent service requests by SR id or subject",
            "/history sr_id - broader service request history",
            "/job_packet sr_id - compact field packet for one service request",
            "/labor sr_id - labor recorded against the service request",
            "/materials sr_id - materials recorded against the service request",
            "/notes sr_id - recent service request notes",
            "/search_address text - address search is limited on this BlueFolder tenant",
            "/search_customer text - search the BlueFolder customer directory",
            "/site sr_id - site address and site notes",
            "/sr sr_id - service request summary",
            "/troubleshoot sr_id - pull recent diagnosis/work context",
            "/user user_id - BlueFolder user lookup",
            "/customer_lookup customer_id - BlueFolder customer lookup",
        ],
        "Workflow Updates": [
            "/access_issue sr_id details - log an access problem",
            "/complete sr_id - complete your assigned job",
            "/damaged_part sr_id details - log a damaged part issue",
            "/enroute sr_id [minutes] - mark yourself en route and optionally record ETA",
            "/eta sr_id minutes - update ETA on your assigned job",
            "/missing_part sr_id details - log a missing part issue",
            "/no_answer sr_id [details] - log that the customer did not answer",
            "/not_home sr_id [details] - log that the customer was not home",
            "/note_add sr_id text - add an internal service request note",
            "/start sr_id - mark yourself started on your assigned job",
        ],
    }
    return [(title, sorted(sections[title])) for title in sorted(sections)]


def _matching_techs_for_member_record(
    member: dict[str, object],
    techs: list[dict[str, object]],
) -> list[dict[str, object]]:
    techs_by_name: dict[str, list[dict[str, object]]] = {}
    for tech in techs:
        normalized = _normalize_name(str(tech.get("name") or ""))
        if not normalized:
            continue
        techs_by_name.setdefault(normalized, []).append(tech)

    unique_matches: dict[int, dict[str, object]] = {}
    for candidate in _member_name_candidates_from_record(member):
        for tech in techs_by_name.get(candidate, []):
            tech_id = int(tech.get("id") or 0)
            if tech_id:
                unique_matches[tech_id] = tech
    return list(unique_matches.values())


def _near_match_techs_for_member_record(
    member: dict[str, object],
    techs: list[dict[str, object]],
    *,
    threshold: float = 0.84,
) -> list[dict[str, object]]:
    candidates = _member_name_candidates_from_record(member)
    scored: list[tuple[float, dict[str, object]]] = []
    for tech in techs:
        tech_name = _normalize_name(str(tech.get("name") or ""))
        if not tech_name:
            continue
        best = max((SequenceMatcher(None, candidate, tech_name).ratio() for candidate in candidates), default=0.0)
        if best >= threshold:
            scored.append((best, tech))

    scored.sort(key=lambda item: (-item[0], str(item[1].get("name") or "")))
    unique: dict[int, dict[str, object]] = {}
    for score, tech in scored[:5]:
        tech_id = int(tech.get("id") or 0)
        if tech_id and tech_id not in unique:
            unique[tech_id] = {
                "id": tech_id,
                "name": tech.get("name"),
                "score": round(score, 3),
            }
    return list(unique.values())


def _name_candidates(member: discord.Member) -> list[str]:
    seen: set[str] = set()
    candidates: list[str] = []
    for raw in [member.display_name, member.global_name, member.name]:
        normalized = _normalize_name(raw)
        if normalized and normalized not in seen:
            seen.add(normalized)
            candidates.append(normalized)
    return candidates


def _build_tech_map_suggestion(
    members: list[dict[str, object]],
    techs: list[dict[str, object]],
) -> dict[str, object]:
    suggested_map: dict[str, int] = {}
    matched: list[dict[str, object]] = []
    ambiguous: list[dict[str, object]] = []
    near_matches: list[dict[str, object]] = []
    unmatched_discord: list[dict[str, object]] = []
    matched_tech_ids: set[int] = set()

    for member in members:
        unique_matches = _matching_techs_for_member_record(member, techs)

        if len(unique_matches) == 1:
            tech = unique_matches[0]
            tech_id = int(tech["id"])
            suggested_map[str(member["discord_user_id"])] = tech_id
            matched_tech_ids.add(tech_id)
            matched.append(
                {
                    "discord_user_id": member["discord_user_id"],
                    "display_name": member.get("display_name"),
                    "username": member.get("username"),
                    "bluefolder_user_id": tech_id,
                    "bluefolder_name": tech.get("name"),
                }
            )
        elif len(unique_matches) > 1:
            ambiguous.append(
                {
                    "discord_user_id": member["discord_user_id"],
                    "display_name": member.get("display_name"),
                    "username": member.get("username"),
                    "candidate_bluefolder_users": [
                        {"id": int(tech["id"]), "name": tech.get("name")}
                        for tech in unique_matches
                    ],
                }
            )
        else:
            nearby = _near_match_techs_for_member_record(member, techs)
            if nearby:
                near_matches.append(
                    {
                        "discord_user_id": member["discord_user_id"],
                        "display_name": member.get("display_name"),
                        "username": member.get("username"),
                        "candidate_bluefolder_users": nearby,
                    }
                )
            unmatched_discord.append(member)

    unmatched_bluefolder = [
        {"id": int(tech["id"]), "name": tech.get("name"), "email": tech.get("email")}
        for tech in techs
        if int(tech.get("id") or 0) not in matched_tech_ids
    ]

    return {
        "suggested_discord_tech_map": suggested_map,
        "suggested_discord_tech_map_env": f"DISCORD_TECH_MAP={json.dumps(suggested_map, separators=(',', ':'))}",
        "matched": matched,
        "ambiguous": ambiguous,
        "near_matches": near_matches,
        "unmatched_discord": unmatched_discord,
        "unmatched_bluefolder": unmatched_bluefolder,
    }


def _require_guild_admin(interaction: discord.Interaction) -> bool:
    perms = getattr(interaction.user, "guild_permissions", None)
    return bool(perms and perms.manage_guild)


def _member_role_names(interaction: discord.Interaction) -> set[str]:
    roles = getattr(interaction.user, "roles", []) or []
    names: set[str] = set()
    for role in roles:
        name = getattr(role, "name", None)
        if name:
            names.add(str(name).casefold())
    return names


def _has_configured_role(interaction: discord.Interaction, role_names: set[str]) -> bool:
    if not role_names:
        return False
    return bool(_member_role_names(interaction) & role_names)


def _record_role_names(record: dict[str, object]) -> set[str]:
    return {
        str(name).casefold()
        for name in (record.get("role_names") or [])
        if str(name).strip()
    }


def _record_has_configured_role(record: dict[str, object], role_names: set[str]) -> bool:
    if not role_names:
        return False
    return bool(_record_role_names(record) & role_names)


def _require_dispatch_access(interaction: discord.Interaction) -> bool:
    if _require_guild_admin(interaction):
        return True
    return _has_configured_role(interaction, settings.parsed_discord_dispatcher_roles)


def _require_parts_access(interaction: discord.Interaction) -> bool:
    if _require_guild_admin(interaction):
        return True
    if _has_configured_role(interaction, settings.parsed_discord_dispatcher_roles):
        return True
    return _has_configured_role(interaction, settings.parsed_discord_parts_roles)


def _role_labels(interaction: discord.Interaction) -> list[str]:
    labels: list[str] = []
    if _require_guild_admin(interaction):
        labels.append("guild_admin")
    if _has_configured_role(interaction, settings.parsed_discord_dispatcher_roles):
        labels.append("dispatcher")
    if _has_configured_role(interaction, settings.parsed_discord_parts_roles):
        labels.append("parts")
    if _has_configured_role(interaction, settings.parsed_discord_tech_roles):
        labels.append("tech")
    return labels


async def _collect_members(
    interaction: discord.Interaction,
    *,
    scope: str,
) -> list[dict[str, object]]:
    guild = interaction.guild
    if guild is None:
        return []

    members: list[discord.Member]
    if scope == "channel":
        channel = interaction.channel
        members = list(getattr(channel, "members", []) or [])
    else:
        members = [member async for member in guild.fetch_members(limit=None)]

    exported: list[dict[str, object]] = []
    for member in sorted(members, key=lambda item: (item.display_name.casefold(), item.name.casefold(), item.id)):
        if member.bot:
            continue
        exported.append(
            {
                "discord_user_id": str(member.id),
                "username": member.name,
                "display_name": member.display_name,
                "global_name": member.global_name,
                "role_names": sorted(role.name for role in getattr(member, "roles", []) if getattr(role, "name", None)),
            }
        )
    return exported


def _alert_tech_label(interaction: discord.Interaction) -> str:
    discord_name = (
        getattr(interaction.user, "display_name", None)
        or getattr(interaction.user, "global_name", None)
        or getattr(interaction.user, "name", None)
        or "Unknown tech"
    )
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        return discord_name

    tech_name = None
    for tech in bot.bluefolder.list_active_techs():
        if tech.get("id") == tech_id:
            tech_name = tech.get("name")
            break
    if tech_name:
        return f"{discord_name} ({tech_name} / BlueFolder {tech_id})"
    return f"{discord_name} (BlueFolder {tech_id})"


def _discord_member_record(interaction: discord.Interaction) -> dict[str, object]:
    return {
        "discord_user_id": str(interaction.user.id),
        "username": interaction.user.name,
        "display_name": getattr(interaction.user, "display_name", interaction.user.name),
        "global_name": getattr(interaction.user, "global_name", None),
        "role_names": sorted(role.name for role in getattr(interaction.user, "roles", []) if getattr(role, "name", None)),
    }


def _discord_member_record_from_member(member: discord.abc.User) -> dict[str, object]:
    return {
        "discord_user_id": str(member.id),
        "username": member.name,
        "display_name": getattr(member, "display_name", member.name),
        "global_name": getattr(member, "global_name", None),
        "role_names": sorted(role.name for role in getattr(member, "roles", []) if getattr(role, "name", None)),
    }


async def _send_write_preview(
    interaction: discord.Interaction,
    *,
    action: str,
    sr_id: int,
    preview_lines: list[str],
) -> None:
    lines = [
        f"Preview only: `{action}` for service request `{sr_id}`.",
        *preview_lines,
        "Run the command again with `confirm:true` to write this update.",
    ]
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


def _job_packet_lines(
    item: dict[str, object],
    *,
    notes: list[dict[str, object]] | None = None,
    assignment: dict[str, object] | None = None,
) -> list[str]:
    lines = [
        f"SR {item.get('id') or '?'}",
        f"Subject: {item.get('subject') or 'n/a'}",
        f"Status: {item.get('status') or 'n/a'}",
        f"Priority: {item.get('priority') or 'n/a'}",
        f"Customer: {item.get('customer_name') or 'n/a'}",
        f"Address: {item.get('address') or 'n/a'}",
    ]
    if assignment:
        lines.append(
            f"Scheduled: {assignment.get('start_display') or assignment.get('start') or 'unscheduled'}"
        )
    if item.get("customer_phone"):
        lines.append(f"Phone: {item.get('customer_phone')}")
    if item.get("customer_email"):
        lines.append(f"Email: {item.get('customer_email')}")
    if item.get("site_notes"):
        lines.append(f"Site Notes: {str(item.get('site_notes'))[:220]}")
    if notes:
        latest = notes[0]
        lines.append(
            f"Latest note: {(latest.get('entryType') or 'Note')} | {latest.get('dateCreated') or 'unknown'}"
        )
        if latest.get("text"):
            lines.append(f"Latest text: {str(latest.get('text'))[:220]}")
    return lines


async def _send_channel_alert(
    interaction: discord.Interaction,
    *,
    title: str,
    sr_id: int,
    note_text: str,
    channel_id: int | None,
    enabled: bool,
    customer_name: str | None = None,
    address: str | None = None,
) -> str | None:
    if not enabled:
        return None
    if not channel_id:
        return None

    channel = bot.get_channel(channel_id)
    if channel is None:
        try:
            channel = await bot.fetch_channel(channel_id)
        except Exception:
            return "Dispatcher alert channel could not be loaded."

    lines = [
        f"**{title}**",
        f"Tech: {_alert_tech_label(interaction)}",
        f"SR: {sr_id}",
    ]
    if customer_name:
        lines.append(f"Customer: {customer_name}")
    if address:
        lines.append(f"Address: {address}")
    lines.append(f"Update: {note_text}")
    try:
        await channel.send("\n".join(lines))
    except Exception:
        return "Dispatcher alert could not be sent."
    return f"Dispatcher alert sent to <#{channel_id}>."


@bot.tree.command(description="Basic bot connectivity check.")
async def ping(interaction: discord.Interaction) -> None:
    await interaction.response.send_message("pong", ephemeral=True)


@bot.tree.command(name="help", description="List Parts Cannon slash commands.")
async def help_command(interaction: discord.Interaction) -> None:
    sections = _help_sections()
    first_message = "\n".join(
        [
            "**Parts Cannon Commands**",
            "",
            f"**{sections[0][0]}**",
            *sections[0][1],
        ]
    )
    await interaction.response.send_message(first_message, ephemeral=True)
    for title, commands_in_section in sections[1:]:
        await interaction.followup.send(
            "\n".join([f"**{title}**", *commands_in_section]),
            ephemeral=True,
        )


@bot.tree.command(name="who_am_i_mapped_to", description="Show your Discord to BlueFolder tech mapping status.")
async def who_am_i_mapped_to(interaction: discord.Interaction) -> None:
    record = _discord_member_record(interaction)
    techs = bot.bluefolder.list_active_techs()
    direct_map = settings.parsed_discord_tech_map.get(str(interaction.user.id))
    matched_techs = _matching_techs_for_member_record(record, techs)

    lines = [
        f"Discord user: {record['display_name']} (@{record['username']})",
        f"Discord ID: {interaction.user.id}",
    ]
    if direct_map:
        mapped_tech = next((tech for tech in techs if int(tech.get('id') or 0) == int(direct_map)), None)
        if mapped_tech:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: {mapped_tech['name']} (BlueFolder {mapped_tech['id']})")
        else:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: BlueFolder {direct_map} (not found in active tech list)")
    else:
        lines.append("Mapped via `DISCORD_TECH_MAP`: no")

    if len(matched_techs) == 1:
        tech = matched_techs[0]
        lines.append(f"Name-based match: {tech['name']} (BlueFolder {tech['id']})")
    elif len(matched_techs) > 1:
        lines.append(
            "Name-based matches: " + ", ".join(f"{tech['name']} ({tech['id']})" for tech in matched_techs[:5])
        )
    else:
        lines.append("Name-based match: none")

    if not direct_map and len(matched_techs) != 1:
        lines.append("Ask an admin to run `/suggest_tech_map` or update `DISCORD_TECH_MAP`.")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="tech_map_status", description="Show Discord-to-BlueFolder tech mapping coverage.")
@app_commands.describe(scope="Audit all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def tech_map_status(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to audit tech mappings.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    techs = bot.bluefolder.list_active_techs()
    active_tech_ids = {int(tech.get("id") or 0) for tech in techs}
    configured_map = settings.parsed_discord_tech_map

    explicit_mapped = 0
    auto_resolvable = 0
    ambiguous = 0
    near_match_only = 0
    unmatched = 0
    stale_mapped = 0
    sample_lines: list[str] = []

    for member in records:
        discord_user_id = str(member["discord_user_id"])
        mapped_tech_id = configured_map.get(discord_user_id)
        matches = _matching_techs_for_member_record(member, techs)

        if mapped_tech_id:
            explicit_mapped += 1
            if int(mapped_tech_id) not in active_tech_ids:
                stale_mapped += 1
                sample_lines.append(
                    f"stale map: {member.get('display_name') or member.get('username')} -> BlueFolder {mapped_tech_id}"
                )
            continue
        if len(matches) == 1:
            auto_resolvable += 1
            if len(sample_lines) < 8:
                tech = matches[0]
                sample_lines.append(
                    f"auto match: {member.get('display_name') or member.get('username')} -> {tech.get('name')} ({tech.get('id')})"
                )
        elif len(matches) > 1:
            ambiguous += 1
            if len(sample_lines) < 8:
                sample_lines.append(
                    f"ambiguous: {member.get('display_name') or member.get('username')}"
                )
        else:
            nearby = _near_match_techs_for_member_record(member, techs)
            if nearby:
                near_match_only += 1
                if len(sample_lines) < 8:
                    best = nearby[0]
                    sample_lines.append(
                        f"near match: {member.get('display_name') or member.get('username')} -> {best.get('name')} ({best.get('id')}, score {best.get('score')})"
                    )
                continue
            unmatched += 1
            if len(sample_lines) < 8:
                sample_lines.append(
                    f"unmatched: {member.get('display_name') or member.get('username')}"
                )

    lines = [
        f"Scope: {scope.value}",
        f"Discord members checked: {len(records)}",
        f"Active BlueFolder techs: {len(techs)}",
        f"Explicitly mapped in env: {explicit_mapped}",
        f"Auto-resolvable by exact name: {auto_resolvable}",
        f"Ambiguous exact-name matches: {ambiguous}",
        f"Near-match review candidates: {near_match_only}",
        f"Unmatched: {unmatched}",
    ]
    if stale_mapped:
        lines.append(f"Mapped to inactive/missing BlueFolder IDs: {stale_mapped}")
    if sample_lines:
        lines.append("")
        lines.append("Examples:")
        lines.extend(sample_lines)

    for idx, chunk in enumerate(_chunk_lines(lines)):
        if idx == 0:
            await interaction.followup.send(chunk, ephemeral=True)
        else:
            await interaction.followup.send(chunk, ephemeral=True)


@bot.tree.command(name="lookup_member", description="Inspect one Discord member's BlueFolder mapping status.")
@app_commands.describe(user="Discord member to inspect.")
async def lookup_member(
    interaction: discord.Interaction,
    user: discord.Member,
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to inspect another member's mapping.",
            ephemeral=True,
        )
        return

    techs = bot.bluefolder.list_active_techs()
    record = _discord_member_record_from_member(user)
    direct_map = settings.parsed_discord_tech_map.get(str(user.id))
    matched_techs = _matching_techs_for_member_record(record, techs)

    lines = [
        f"Discord user: {record['display_name']} (@{record['username']})",
        f"Discord ID: {user.id}",
    ]
    role_names = sorted(_record_role_names(record))
    if role_names:
        lines.append("Configured roles: " + ", ".join(role_names))
    if direct_map:
        mapped_tech = next((tech for tech in techs if int(tech.get('id') or 0) == int(direct_map)), None)
        if mapped_tech:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: {mapped_tech['name']} (BlueFolder {mapped_tech['id']})")
        else:
            lines.append(f"Mapped via `DISCORD_TECH_MAP`: BlueFolder {direct_map} (not found in active tech list)")
    else:
        lines.append("Mapped via `DISCORD_TECH_MAP`: no")

    if len(matched_techs) == 1:
        tech = matched_techs[0]
        lines.append(f"Name-based match: {tech['name']} (BlueFolder {tech['id']})")
    elif len(matched_techs) > 1:
        lines.append(
            "Name-based matches: " + ", ".join(f"{tech['name']} ({tech['id']})" for tech in matched_techs[:5])
        )
    else:
        lines.append("Name-based match: none")

    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="role_audit", description="Summarize configured Discord role coverage.")
@app_commands.describe(scope="Audit all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def role_audit(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to audit roles.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    tech_count = sum(1 for record in records if _record_has_configured_role(record, settings.parsed_discord_tech_roles))
    dispatcher_count = sum(1 for record in records if _record_has_configured_role(record, settings.parsed_discord_dispatcher_roles))
    parts_count = sum(1 for record in records if _record_has_configured_role(record, settings.parsed_discord_parts_roles))
    no_configured_role = sum(
        1
        for record in records
        if not _record_has_configured_role(record, settings.parsed_discord_tech_roles)
        and not _record_has_configured_role(record, settings.parsed_discord_dispatcher_roles)
        and not _record_has_configured_role(record, settings.parsed_discord_parts_roles)
    )

    lines = [
        f"Scope: {scope.value}",
        f"Members checked: {len(records)}",
        f"Tech role matches: {tech_count}",
        f"Dispatcher role matches: {dispatcher_count}",
        f"Parts role matches: {parts_count}",
        f"No configured roles: {no_configured_role}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="mapping_drift", description="Audit role and mapping drift across members.")
@app_commands.describe(scope="Audit all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def mapping_drift(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to audit mapping drift.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    techs = bot.bluefolder.list_active_techs()
    active_tech_ids = {int(tech.get("id") or 0) for tech in techs}
    configured_map = settings.parsed_discord_tech_map

    tech_role_no_map = 0
    env_map_without_tech_role = 0
    stale_env_map = 0
    exact_match_no_tech_role = 0
    sample_lines: list[str] = []

    for record in records:
        discord_user_id = str(record["discord_user_id"])
        has_tech_role = _record_has_configured_role(record, settings.parsed_discord_tech_roles)
        mapped_tech_id = configured_map.get(discord_user_id)
        exact_matches = _matching_techs_for_member_record(record, techs)

        if has_tech_role and not mapped_tech_id and len(exact_matches) != 1:
            tech_role_no_map += 1
            if len(sample_lines) < 8:
                sample_lines.append(f"tech role, no clear map: {record.get('display_name') or record.get('username')}")
        if mapped_tech_id and not has_tech_role:
            env_map_without_tech_role += 1
            if len(sample_lines) < 8:
                sample_lines.append(f"mapped, no tech role: {record.get('display_name') or record.get('username')} -> {mapped_tech_id}")
        if mapped_tech_id and int(mapped_tech_id) not in active_tech_ids:
            stale_env_map += 1
            if len(sample_lines) < 8:
                sample_lines.append(f"stale env map: {record.get('display_name') or record.get('username')} -> {mapped_tech_id}")
        if len(exact_matches) == 1 and not has_tech_role:
            exact_match_no_tech_role += 1
            if len(sample_lines) < 8:
                tech = exact_matches[0]
                sample_lines.append(
                    f"exact BF match, no tech role: {record.get('display_name') or record.get('username')} -> {tech.get('name')} ({tech.get('id')})"
                )

    lines = [
        f"Scope: {scope.value}",
        f"Members checked: {len(records)}",
        f"Tech role but no clear map: {tech_role_no_map}",
        f"Mapped in env but missing tech role: {env_map_without_tech_role}",
        f"Stale env tech maps: {stale_env_map}",
        f"Exact BlueFolder match but missing tech role: {exact_match_no_tech_role}",
    ]
    if sample_lines:
        lines.append("")
        lines.append("Examples:")
        lines.extend(sample_lines)
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="export_member_map", description="Export Discord user ids and names to a JSON file.")
@app_commands.describe(scope="Export all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def export_member_map(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to export member ids.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    export_file = export_output_path()
    export_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "guild_id": str(interaction.guild_id or ""),
        "scope": scope.value,
        "member_count": len(records),
        "members": records,
        "discord_tech_map_template": {item["discord_user_id"]: None for item in records},
    }
    export_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    await interaction.followup.send(
        f"Wrote {len(records)} member records to `{export_file}`.",
        ephemeral=True,
    )


@bot.tree.command(name="suggest_tech_map", description="Suggest a DISCORD_TECH_MAP by matching Discord names to BlueFolder techs.")
@app_commands.describe(scope="Compare either all guild members or just members visible in this channel.")
@app_commands.choices(
    scope=[
        app_commands.Choice(name="guild", value="guild"),
        app_commands.Choice(name="channel", value="channel"),
    ]
)
async def suggest_tech_map(
    interaction: discord.Interaction,
    scope: app_commands.Choice[str],
) -> None:
    if not _require_guild_admin(interaction):
        await interaction.response.send_message(
            "You need `Manage Server` permission to build a tech-map suggestion.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    records = await _collect_members(interaction, scope=scope.value)
    techs = bot.bluefolder.list_active_techs()
    suggestion = _build_tech_map_suggestion(records, techs)

    export_file = export_output_path()
    export_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "guild_id": str(interaction.guild_id or ""),
        "scope": scope.value,
        "member_count": len(records),
        "bluefolder_tech_count": len(techs),
        **suggestion,
    }
    suggestion_path = export_output_path(stem_suffix="_suggested_map")
    suggestion_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    env_path = export_output_path(stem_suffix="_tech_map", extension=".env")
    env_path.write_text(f"{suggestion['suggested_discord_tech_map_env']}\n", encoding="utf-8")

    await interaction.followup.send(
        (
            f"Wrote suggested tech map to `{suggestion_path}` and env snippet to `{env_path}`. "
            f"Matched {len(suggestion['matched'])}, ambiguous {len(suggestion['ambiguous'])}, "
            f"near matches {len(suggestion['near_matches'])}, "
            f"unmatched Discord {len(suggestion['unmatched_discord'])}, "
            f"unmatched BlueFolder {len(suggestion['unmatched_bluefolder'])}."
        ),
        ephemeral=True,
    )


@bot.tree.command(name="techs", description="List active BlueFolder technicians.")
async def techs(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_list = bot.bluefolder.list_active_techs()
    if not tech_list:
        await interaction.followup.send("No active technicians found.", ephemeral=True)
        return

    lines = [f"{t['id']} - {t['name']}" for t in tech_list[:25]]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="my_jobs", description="Show today's assignments for your mapped technician account.")
async def my_jobs(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send("No assignments found for you today.", ephemeral=True)
        return

    lines = []
    for idx, item in enumerate(assignments[:15], start=1):
        start = item.get("start_display") or "unscheduled"
        sr_id = item.get("service_request_id") or "?"
        subject = item.get("subject") or "Service Request"
        lines.append(f"{idx}. {start} - SR {sr_id} - {subject}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="my_day", description="Show your assignments for a specific day.")
@app_commands.describe(date_iso="Date in YYYY-MM-DD format")
async def my_day(interaction: discord.Interaction, date_iso: str) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    day = _parse_iso_date(date_iso)
    if not day:
        await interaction.followup.send("Date must be in YYYY-MM-DD format.", ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_day(tech_id, day)
    if not assignments:
        await interaction.followup.send(f"No assignments found for you on `{day.isoformat()}`.", ephemeral=True)
        return

    lines = [f"Assignments for {day.isoformat()}:"]
    for idx, item in enumerate(assignments[:15], start=1):
        start = item.get("start_display") or item.get("start") or "unscheduled"
        sr_id = item.get("service_request_id") or "?"
        subject = item.get("subject") or "Service Request"
        lines.append(f"{idx}. {start} - SR {sr_id} - {subject}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="my_status", description="Show your mapping, today's job count, and next assignment.")
async def my_status(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    record = _discord_member_record(interaction)
    techs = bot.bluefolder.list_active_techs()
    direct_map = settings.parsed_discord_tech_map.get(str(interaction.user.id))
    matched_techs = _matching_techs_for_member_record(record, techs)
    tech_id = _my_tech_id(interaction)

    lines = [
        f"Discord user: {record['display_name']} (@{record['username']})",
        f"Discord ID: {interaction.user.id}",
    ]
    labels = _role_labels(interaction)
    if labels:
        lines.append("Detected roles: " + ", ".join(labels))
    if direct_map:
        mapped_tech = next((tech for tech in techs if int(tech.get('id') or 0) == int(direct_map)), None)
        if mapped_tech:
            lines.append(f"Mapped via env: {mapped_tech['name']} (BlueFolder {mapped_tech['id']})")
        else:
            lines.append(f"Mapped via env: BlueFolder {direct_map} (not found in active tech list)")
    elif len(matched_techs) == 1:
        tech = matched_techs[0]
        lines.append(f"Mapped by exact name: {tech['name']} (BlueFolder {tech['id']})")
    elif len(matched_techs) > 1:
        lines.append("Mapped by exact name: ambiguous")
    else:
        lines.append("Mapped: no")

    if not tech_id:
        lines.append("Today's assignments: unavailable until your Discord user maps to a BlueFolder tech.")
        await interaction.followup.send("\n".join(lines), ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    lines.append(f"Today's assignments: {len(assignments)}")
    if assignments:
        next_item = assignments[0]
        lines.extend(
            [
                f"Next SR: {next_item.get('service_request_id') or '?'}",
                f"Next start: {next_item.get('start_display') or next_item.get('start') or 'unscheduled'}",
                f"Next subject: {next_item.get('subject') or 'Service Request'}",
            ]
        )
    else:
        lines.append("Next assignment: none scheduled today")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="my_week", description="Show your assignment counts for the next 7 days.")
async def my_week(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    start_day = date.today()
    end_day = start_day + timedelta(days=6)
    assignments = bot.bluefolder.get_assignments_for_user_window(
        tech_id,
        start_day=start_day,
        end_day=end_day,
    )
    by_day: dict[str, list[dict[str, object]]] = {}
    for item in assignments:
        raw_start = str(item.get("start") or "")
        day_key = raw_start[:10] if len(raw_start) >= 10 else start_day.isoformat()
        by_day.setdefault(day_key, []).append(item)

    lines = [f"Assignments for {start_day.isoformat()} through {end_day.isoformat()}:"]
    for offset in range(7):
        day = start_day + timedelta(days=offset)
        bucket = by_day.get(day.isoformat(), [])
        if bucket:
            first = bucket[0]
            lines.append(
                f"{day.isoformat()}: {len(bucket)} assignment(s), first at {first.get('start_display') or first.get('start') or 'unscheduled'}"
            )
        else:
            lines.append(f"{day.isoformat()}: 0 assignments")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="my_next_packet", description="Show a compact packet for your next assignment.")
async def my_next_packet(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send("No assignments found for you today.", ephemeral=True)
        return

    assignment = assignments[0]
    sr_id = int(assignment.get("service_request_id") or 0)
    if not sr_id:
        await interaction.followup.send("Your next assignment does not have a service request ID.", ephemeral=True)
        return

    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    notes = bot.bluefolder.get_service_request_notes(sr_id, limit=2)
    await interaction.followup.send(
        "\n".join(_job_packet_lines(item, notes=notes, assignment=assignment)),
        ephemeral=True,
    )


@bot.tree.command(name="today_board", description="Show today's assignment load snapshot for dispatch.")
async def today_board(interaction: discord.Interaction) -> None:
    if not _require_dispatch_access(interaction):
        await interaction.response.send_message(
            "You need a configured dispatcher role or `Manage Server` permission for this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    loads = bot.bluefolder.get_dispatch_loads_for_day(date.today(), limit=15)
    if not loads:
        await interaction.followup.send("No tech load data found for today.", ephemeral=True)
        return

    zero_count = sum(1 for item in loads if int(item.get("assignment_count") or 0) == 0)
    heavy_count = sum(1 for item in loads if int(item.get("assignment_count") or 0) >= 5)
    lines = [
        f"Today Board ({date.today().isoformat()}):",
        f"Techs shown: {len(loads)} | idle: {zero_count} | heavy load (5+): {heavy_count}",
    ]
    for item in loads:
        first_start = item.get("first_start") or "no start time"
        last_end = item.get("last_end") or "no end time"
        lines.append(
            f"{item.get('tech_name') or 'Unknown'} ({item.get('tech_id')}): {item.get('assignment_count')} assignment(s), first at {first_start}, last end {last_end}"
        )
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="next_openings", description="Show which techs are lightest today.")
async def next_openings(interaction: discord.Interaction) -> None:
    if not _require_dispatch_access(interaction):
        await interaction.response.send_message(
            "You need a configured dispatcher role or `Manage Server` permission for this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    loads = bot.bluefolder.get_dispatch_loads_for_day(date.today(), limit=15)
    if not loads:
        await interaction.followup.send("No tech load data found for today.", ephemeral=True)
        return

    ranked = sorted(
        loads,
        key=lambda item: (
            int(item.get("assignment_count") or 0),
            item.get("first_start") or "",
            str(item.get("tech_name") or "").casefold(),
        ),
    )
    lines = [f"Next Openings ({date.today().isoformat()}):"]
    for item in ranked[:8]:
        lines.append(
            f"{item.get('tech_name') or 'Unknown'} ({item.get('tech_id')}): {item.get('assignment_count')} assignment(s), first at {item.get('first_start') or 'no start time'}"
        )
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="sr_brief", description="Show a compact dispatch summary for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def sr_brief(interaction: discord.Interaction, sr_id: int) -> None:
    if not _require_dispatch_access(interaction):
        await interaction.response.send_message(
            "You need a configured dispatcher role or `Manage Server` permission for this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    notes = bot.bluefolder.get_service_request_notes(sr_id, limit=2)
    assignments = bot.bluefolder.find_sr_assignment_window(
        sr_id,
        start_day=date.today(),
        end_day=date.today() + timedelta(days=7),
    )

    lines = [
        f"SR {item['id']}",
        f"Subject: {item.get('subject') or 'n/a'}",
        f"Status: {item.get('status') or 'n/a'}",
        f"Priority: {item.get('priority') or 'n/a'}",
        f"Customer: {item.get('customer_name') or 'n/a'}",
        f"Address: {item.get('address') or 'n/a'}",
    ]
    if assignments:
        lines.append(
            "Assignments: " + "; ".join(
                f"{row.get('tech_name')} {row.get('start') or 'unscheduled'}"
                for row in assignments[:3]
            )
        )
    else:
        lines.append("Assignments: none found in next 7 days")
    if notes:
        latest = notes[0]
        lines.append(
            f"Latest note: {(latest.get('entryType') or 'Note')} | {latest.get('dateCreated') or 'unknown'}"
        )
        if latest.get("text"):
            lines.append(f"Latest text: {latest['text'][:200]}")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="parts_brief", description="Show a compact parts-facing summary for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def parts_brief(interaction: discord.Interaction, sr_id: int) -> None:
    if not _require_parts_access(interaction):
        await interaction.response.send_message(
            "You need a configured parts/dispatcher role or `Manage Server` permission for this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    part_notes = bot.bluefolder.get_recent_part_notes(sr_id, limit=3)
    lines = [
        f"SR {item['id']}",
        f"Subject: {item.get('subject') or 'n/a'}",
        f"Customer: {item.get('customer_name') or 'n/a'}",
        f"Address: {item.get('address') or 'n/a'}",
    ]
    if part_notes:
        latest = part_notes[0]
        lines.append(
            f"Latest parts note: {(latest.get('entryType') or 'Note')} | {latest.get('dateCreated') or 'unknown'}"
        )
        if latest.get("text"):
            lines.append(f"Latest text: {latest['text'][:220]}")
    else:
        lines.append("No recent parts-related notes found.")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="parts_notes", description="Show recent parts-related notes for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def parts_notes(interaction: discord.Interaction, sr_id: int) -> None:
    if not _require_parts_access(interaction):
        await interaction.response.send_message(
            "You need a configured parts/dispatcher role or `Manage Server` permission for this command.",
            ephemeral=True,
        )
        return

    await interaction.response.defer(ephemeral=True)
    notes = bot.bluefolder.get_recent_part_notes(sr_id, limit=6)
    if not notes:
        await interaction.followup.send(f"No recent parts-related notes found for `{sr_id}`.", ephemeral=True)
        return

    blocks = []
    for idx, note in enumerate(notes, start=1):
        blocks.append(
            "\n".join(
                [
                    f"**{idx}. {(note.get('entryType') or 'Note')}**",
                    f"`{note.get('dateCreated') or 'unknown'}` by **{note.get('author') or 'Unknown'}**",
                    note.get("text") or "",
                ]
            )
        )
    await interaction.followup.send("\n\n---\n\n".join(blocks), ephemeral=True)


@bot.tree.command(name="next_job", description="Show your next scheduled assignment today.")
async def next_job(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send("No assignments found for you today.", ephemeral=True)
        return

    item = assignments[0]
    lines = [
        f"SR {item.get('service_request_id') or '?'}",
        f"Start: {item.get('start_display') or item.get('start') or 'unscheduled'}",
        f"End: {item.get('end_display') or item.get('end') or 'n/a'}",
        f"Subject: {item.get('subject') or 'Service Request'}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="assignments_today", description="Show today's assignments for a technician.")
@app_commands.describe(tech_id="BlueFolder technician user ID")
async def assignments_today(interaction: discord.Interaction, tech_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    assignments = bot.bluefolder.get_assignments_for_user_today(tech_id)
    if not assignments:
        await interaction.followup.send(f"No assignments found today for tech `{tech_id}`.", ephemeral=True)
        return

    lines = []
    for idx, item in enumerate(assignments[:15], start=1):
        sr_id = item.get("service_request_id") or "?"
        start = item.get("start_display") or item.get("start") or "unscheduled"
        subject = item.get("subject") or "Service Request"
        lines.append(f"{idx}. SR {sr_id} - {start} - {subject}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="sr", description="Look up a BlueFolder service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def sr(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    lines = [
        f"SR {item['id']}",
        f"Subject: {item.get('subject') or 'n/a'}",
        f"Status: {item.get('status') or 'n/a'}",
        f"Priority: {item.get('priority') or 'n/a'}",
    ]
    if item.get("address"):
        lines.append(f"Address: {item['address']}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="job_packet", description="Show a compact field packet for one service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def job_packet(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return
    notes = bot.bluefolder.get_service_request_notes(sr_id, limit=2)
    await interaction.followup.send(
        "\n".join(_job_packet_lines(item, notes=notes)),
        ephemeral=True,
    )


@bot.tree.command(name="customer", description="Show customer details and contacts for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def customer(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    lines = [
        f"Customer: {item.get('customer_name') or 'n/a'}",
        f"Phone: {item.get('customer_phone') or 'n/a'}",
        f"Email: {item.get('customer_email') or 'n/a'}",
    ]
    for contact in item.get("contacts", [])[:3]:
        bits = [contact["name"]]
        if contact.get("title"):
            bits.append(contact["title"])
        if contact.get("phone"):
            bits.append(contact["phone"])
        if contact.get("email"):
            bits.append(contact["email"])
        prefix = "Primary Contact" if contact.get("is_primary") else "Contact"
        lines.append(f"{prefix}: {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="site", description="Show site address and site notes for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def site(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_service_request(sr_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for `{sr_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Service request `{sr_id}` not found.", ephemeral=True)
        return

    lines = [
        f"Site: {item.get('site_name') or 'n/a'}",
        f"Address: {item.get('address') or 'n/a'}",
    ]
    if item.get("site_notes"):
        lines.append(f"Site Notes: {item['site_notes']}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="notes", description="Show recent notes for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def notes(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    comments = bot.bluefolder.get_service_request_notes(sr_id)
    if not comments:
        await interaction.followup.send(f"No recent notes found for `{sr_id}`.", ephemeral=True)
        return

    blocks = []
    for idx, comment in enumerate(comments, start=1):
        date = comment.get("dateCreated") or "unknown"
        author = comment.get("author") or "Unknown"
        text = comment.get("text") or ""
        entry_type = comment.get("entryType") or "Note"
        block = "\n".join(
            [
                f"**{idx}. {entry_type}**",
                f"`{date}` by **{author}**",
                text,
            ]
        )
        blocks.append(block)
    await interaction.followup.send("\n\n---\n\n".join(blocks), ephemeral=True)


@bot.tree.command(name="history", description="Show broader service request history.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def history(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    entries = bot.bluefolder.get_service_request_history(sr_id, limit=10)
    if not entries:
        await interaction.followup.send(f"No history found for `{sr_id}`.", ephemeral=True)
        return

    blocks = []
    for idx, entry in enumerate(entries, start=1):
        blocks.append(
            "\n".join(
                [
                    f"**{idx}. {entry.get('entryType') or 'History'}**",
                    f"`{entry.get('dateCreated') or 'unknown'}` by **{entry.get('author') or 'Unknown'}**",
                    entry.get("text") or "",
                ]
            )
        )
    await interaction.followup.send("\n\n---\n\n".join(blocks), ephemeral=True)


@bot.tree.command(name="note_add", description="Add an internal note to a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", text="Note text to append", confirm="Set true to write the note")
async def note_add(interaction: discord.Interaction, sr_id: int, text: str, confirm: bool = False) -> None:
    if not confirm:
        await _send_write_preview(
            interaction,
            action="note_add",
            sr_id=sr_id,
            preview_lines=[
                "This will add an internal SR note.",
                f"Text: {text[:250]}",
            ],
        )
        return
    await interaction.response.defer(ephemeral=True)
    result = bot.bluefolder.add_service_request_note(
        sr_id,
        text,
        user_id=_my_tech_id(interaction),
        visible_to_customer=False,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not add note to `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(f"Added note to service request `{sr_id}`.", ephemeral=True)


@bot.tree.command(name="troubleshoot", description="Show recent troubleshooting context for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def troubleshoot(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    result = bot.bluefolder.build_troubleshooting_summary(sr_id)
    if result.get("error"):
        await interaction.followup.send(
            f"Could not build troubleshooting summary for `{sr_id}`: {result['error']}",
            ephemeral=True,
        )
        return

    lines = [
        f"SR {result['sr_id']}",
        f"Subject: {result.get('subject') or 'n/a'}",
    ]
    if result.get("customer_name"):
        lines.append(f"Customer: {result['customer_name']}")
    if result.get("address"):
        lines.append(f"Address: {result['address']}")

    sections = result.get("sections") or {}
    if sections:
        label_map = {
            "complaint": "Complaint",
            "diagnosis": "Diagnosis",
            "work_performed": "Work Performed",
            "parts_needed": "Parts Needed",
            "parts_used": "Parts Used",
        }
        for key in ("complaint", "diagnosis", "work_performed", "parts_needed", "parts_used"):
            if sections.get(key):
                lines.append(f"{label_map[key]}: {sections[key]}")
    else:
        lines.append("No structured troubleshooting sections found in recent labor or history.")

    recent_notes = result.get("recent_notes") or []
    if recent_notes:
        latest = recent_notes[0]
        lines.append(
            f"Latest History: {(latest.get('entryType') or 'Note')} | {latest.get('dateCreated') or 'unknown'}"
        )
        if latest.get("text"):
            lines.append(f"Latest Text: {latest['text'][:250]}")

    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="no_answer", description="Log that the customer did not answer.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Optional extra detail", confirm="Set true to write the update")
async def no_answer(interaction: discord.Interaction, sr_id: int, details: str | None = None, confirm: bool = False) -> None:
    if not confirm:
        preview = [
            "This will log a no-answer contact issue and may notify dispatch.",
        ]
        if details:
            preview.append(f"Details: {details[:250]}")
        await _send_write_preview(interaction, action="no_answer", sr_id=sr_id, preview_lines=preview)
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_contact_issue(
        sr_id,
        user_id=tech_id,
        issue_type="no_answer",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log no-answer for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Customer No Answer",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.dispatcher_alert_channel_id,
        enabled=settings.dispatcher_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged no-answer for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="not_home", description="Log that the customer was not home at arrival.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Optional extra detail", confirm="Set true to write the update")
async def not_home(interaction: discord.Interaction, sr_id: int, details: str | None = None, confirm: bool = False) -> None:
    if not confirm:
        preview = [
            "This will log a not-home contact issue and may notify dispatch.",
        ]
        if details:
            preview.append(f"Details: {details[:250]}")
        await _send_write_preview(interaction, action="not_home", sr_id=sr_id, preview_lines=preview)
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_contact_issue(
        sr_id,
        user_id=tech_id,
        issue_type="not_home",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log not-home for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Customer Not Home",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.dispatcher_alert_channel_id,
        enabled=settings.dispatcher_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged not-home for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="access_issue", description="Log an access problem for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Access problem details", confirm="Set true to write the update")
async def access_issue(interaction: discord.Interaction, sr_id: int, details: str, confirm: bool = False) -> None:
    if not confirm:
        await _send_write_preview(
            interaction,
            action="access_issue",
            sr_id=sr_id,
            preview_lines=[
                "This will log an access issue and may notify dispatch.",
                f"Details: {details[:250]}",
            ],
        )
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_contact_issue(
        sr_id,
        user_id=tech_id,
        issue_type="access_issue",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log access issue for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Access Issue",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.dispatcher_alert_channel_id,
        enabled=settings.dispatcher_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged access issue for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="missing_part", description="Log a missing part issue for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Missing part details", confirm="Set true to write the update")
async def missing_part(interaction: discord.Interaction, sr_id: int, details: str, confirm: bool = False) -> None:
    if not confirm:
        await _send_write_preview(
            interaction,
            action="missing_part",
            sr_id=sr_id,
            preview_lines=[
                "This will log a missing-part issue and may notify parts.",
                f"Details: {details[:250]}",
            ],
        )
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_parts_issue(
        sr_id,
        user_id=tech_id,
        issue_type="missing_part",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log missing-part issue for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Missing Part",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.parts_alert_channel_id,
        enabled=settings.parts_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged missing-part issue for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send("\n".join(response_lines), ephemeral=True)


@bot.tree.command(name="damaged_part", description="Log a damaged part issue for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", details="Damaged part details", confirm="Set true to write the update")
async def damaged_part(interaction: discord.Interaction, sr_id: int, details: str, confirm: bool = False) -> None:
    if not confirm:
        await _send_write_preview(
            interaction,
            action="damaged_part",
            sr_id=sr_id,
            preview_lines=[
                "This will log a damaged-part issue and may notify parts.",
                f"Details: {details[:250]}",
            ],
        )
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return
    result = bot.bluefolder.log_parts_issue(
        sr_id,
        user_id=tech_id,
        issue_type="damaged_part",
        details=details,
    )
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not log damaged-part issue for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    alert_status = await _send_channel_alert(
        interaction,
        title="Damaged Part",
        sr_id=sr_id,
        note_text=result.get("note_text") or "",
        channel_id=settings.parts_alert_channel_id,
        enabled=settings.parts_alert_on_contact_issue,
        customer_name=result.get("customer_name"),
        address=result.get("address"),
    )
    response_lines = [
        f"Logged damaged-part issue for service request `{sr_id}`.",
        f"Time: {result.get('logged_at')}",
        result.get("note_text") or "",
    ]
    if alert_status:
        response_lines.append(alert_status)
    await interaction.followup.send("\n".join(response_lines), ephemeral=True)


@bot.tree.command(name="eta", description="Record an ETA update for your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", minutes="Minutes until arrival", confirm="Set true to write the update")
async def eta(interaction: discord.Interaction, sr_id: int, minutes: int, confirm: bool = False) -> None:
    if minutes < 0:
        await interaction.response.send_message("ETA minutes must be zero or greater.", ephemeral=True)
        return
    if not confirm:
        await _send_write_preview(
            interaction,
            action="eta",
            sr_id=sr_id,
            preview_lines=[f"This will record an ETA update for {minutes} minutes."],
        )
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_eta(sr_id, user_id=tech_id, minutes=minutes)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not update ETA for `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Updated ETA for service request `{sr_id}`.",
                f"Stored as: {result.get('stored_as')}",
                f"ETA: {result.get('eta_minutes')} minutes",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="enroute", description="Mark yourself en route and optionally record ETA.")
@app_commands.describe(sr_id="BlueFolder service request ID", minutes="Optional ETA in minutes", confirm="Set true to write the update")
async def enroute(interaction: discord.Interaction, sr_id: int, minutes: int | None = None, confirm: bool = False) -> None:
    if minutes is not None and minutes < 0:
        await interaction.response.send_message("ETA minutes must be zero or greater.", ephemeral=True)
        return
    if not confirm:
        preview = ["This will mark the service request en route."]
        if minutes is not None:
            preview.append(f"It will also record ETA: {minutes} minutes.")
        await _send_write_preview(interaction, action="enroute", sr_id=sr_id, preview_lines=preview)
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_enroute(sr_id, user_id=tech_id, minutes=minutes)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not mark `{sr_id}` en route: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    response_lines = [
        f"Marked service request `{sr_id}` en route.",
        f"Stored as: {result.get('stored_as')}",
        f"Time: {result.get('timestamp')}",
    ]
    if minutes is not None:
        response_lines.append(f"ETA: {result.get('eta_minutes')} minutes")
    await interaction.followup.send(
        "\n".join(response_lines),
        ephemeral=True,
    )


@bot.tree.command(name="start", description="Mark yourself started on your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", confirm="Set true to write the update")
async def start(interaction: discord.Interaction, sr_id: int, confirm: bool = False) -> None:
    if not confirm:
        await _send_write_preview(
            interaction,
            action="start",
            sr_id=sr_id,
            preview_lines=["This will mark the service request as started in the workflow log."],
        )
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_start(sr_id, user_id=tech_id)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not mark `{sr_id}` started: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Marked service request `{sr_id}` started.",
                f"Stored as: {result.get('stored_as')}",
                f"Started: {result.get('started_at')}",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="complete", description="Complete your assigned service request.")
@app_commands.describe(sr_id="BlueFolder service request ID", confirm="Set true to write the update")
async def complete(interaction: discord.Interaction, sr_id: int, confirm: bool = False) -> None:
    if not confirm:
        await _send_write_preview(
            interaction,
            action="complete",
            sr_id=sr_id,
            preview_lines=["This will mark the service request complete in the workflow log."],
        )
        return
    await interaction.response.defer(ephemeral=True)
    tech_id = _my_tech_id(interaction)
    if not tech_id:
        await interaction.followup.send(_my_tech_help(), ephemeral=True)
        return

    result = bot.bluefolder.mark_complete(sr_id, user_id=tech_id)
    if not result.get("ok"):
        await interaction.followup.send(
            f"Could not complete `{sr_id}`: {result.get('error') or 'unknown error'}",
            ephemeral=True,
        )
        return
    await interaction.followup.send(
        "\n".join(
            [
                f"Completed assignment for service request `{sr_id}`.",
                f"Stored as: {result.get('stored_as')}",
                f"Completed: {result.get('completed_at')}",
            ]
        ),
        ephemeral=True,
    )


@bot.tree.command(name="attachments", description="List recent attachments for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def attachments(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_attachments(sr_id)
    if not rows:
        await interaction.followup.send(f"No attachments found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        when = row.get("postedOn") or row.get("dateCreated") or "unknown"
        bits = [row.get("fileName") or "attachment", f"type={row.get('fileType') or 'n/a'}", when]
        if row.get("description"):
            bits.append(row["description"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="equipment", description="List customer equipment for a service request site.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def equipment(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_equipment(sr_id)
    if not rows:
        await interaction.followup.send(f"No equipment found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row.get("name") or "Equipment"]
        if row.get("model"):
            bits.append(f"model={row['model']}")
        if row.get("serialNumber"):
            bits.append(f"serial={row['serialNumber']}")
        if row.get("installDate"):
            bits.append(f"installed={row['installDate']}")
        if row.get("manufacturer"):
            bits.append(f"mfr={row['manufacturer']}")
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="materials", description="List materials recorded against a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def materials(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_materials(sr_id)
    if not rows:
        await interaction.followup.send(f"No materials found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row.get("itemName") or row.get("description") or "Material"]
        if row.get("quantity"):
            bits.append(f"qty={row['quantity']}")
        if row.get("unitPrice"):
            bits.append(f"unit={row['unitPrice']}")
        if row.get("total"):
            bits.append(f"total={row['total']}")
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="labor", description="List labor recorded against a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def labor(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_service_request_labor(sr_id)
    if not rows:
        await interaction.followup.send(f"No labor found for `{sr_id}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row.get("date") or "unknown date"]
        if row.get("hours"):
            bits.append(f"hours={row['hours']}")
        if row.get("rate"):
            bits.append(f"rate={row['rate']}")
        if row.get("total"):
            bits.append(f"total={row['total']}")
        if row.get("description"):
            bits.append(row["description"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="search_customer", description="Search the BlueFolder customer directory.")
@app_commands.describe(text="Customer or subject text")
async def search_customer(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.search_recent_service_requests(text, field="customer")
    if not rows:
        await interaction.followup.send(f"No customers matched `{text}`.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [f"Customer {row.get('id')}", row.get("subject") or "Customer"]
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="find_sr", description="Search recent service requests by SR id or subject.")
@app_commands.describe(text="SR id fragment or subject text")
async def find_sr(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.search_recent_service_requests(text, field="service_request")
    if not rows:
        await interaction.followup.send("No recent service requests matched that search.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [f"SR {row.get('id')}", row.get("subject") or "Service Request"]
        if row.get("tech_name"):
            bits.append(str(row["tech_name"]))
        if row.get("start"):
            bits.append(str(row["start"]))
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="search_address", description="Address search is limited on this BlueFolder tenant.")
@app_commands.describe(text="Address, city, state, or zip text")
async def search_address(interaction: discord.Interaction, text: str) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.search_recent_service_requests(text, field="address")
    if not rows:
        await interaction.followup.send(
            "Address search is not fully supported by the BlueFolder endpoints available on this tenant yet.",
            ephemeral=True,
        )
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [f"SR {row.get('id')}", row.get("subject") or "Service Request"]
        if row.get("address"):
            bits.append(row["address"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="user", description="Look up a BlueFolder user.")
@app_commands.describe(user_id="BlueFolder user ID")
async def user(interaction: discord.Interaction, user_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_user(user_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for user `{user_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"User `{user_id}` not found.", ephemeral=True)
        return

    lines = [
        f"User {item['id']}",
        f"Name: {item.get('name') or 'n/a'}",
        f"Email: {item.get('email') or 'n/a'}",
        f"Type: {item.get('user_type') or 'n/a'}",
        f"Active: {item.get('is_active')}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="customer_lookup", description="Look up a BlueFolder customer.")
@app_commands.describe(customer_id="BlueFolder customer ID")
async def customer_lookup(interaction: discord.Interaction, customer_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    item = bot.bluefolder.get_customer_summary(customer_id)
    if item.get("error"):
        await interaction.followup.send(
            f"BlueFolder lookup failed for customer `{customer_id}`: {item['error']}",
            ephemeral=True,
        )
        return
    if not item:
        await interaction.followup.send(f"Customer `{customer_id}` not found.", ephemeral=True)
        return

    lines = [
        f"Customer {item['id']}",
        f"Name: {item.get('name') or 'n/a'}",
        f"Type: {item.get('type') or 'n/a'}",
        f"Inactive: {item.get('inactive')}",
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="bf_status", description="Show BlueFolder connectivity/config status.")
async def bf_status(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    status = bot.bluefolder.bluefolder_status()
    lines = [
        f"OK: {status.get('ok')}",
        f"Base URL: {status.get('base_url') or 'n/a'}",
        f"Host Header: {status.get('host_header') or 'n/a'}",
        f"Verify SSL: {status.get('verify_ssl')}",
    ]
    if status.get("ok"):
        lines.append(f"Active Techs: {status.get('active_tech_count')}")
    else:
        lines.append(f"Error: {status.get('error') or 'unknown'}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="tech_loads", description="Show today's assignment counts by technician.")
async def tech_loads(interaction: discord.Interaction) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.get_dispatch_loads_for_day(date.today(), limit=15)
    if not rows:
        await interaction.followup.send("No technician load data available.", ephemeral=True)
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [
            row["tech_name"],
            f"jobs={row['assignment_count']}",
        ]
        if row.get("first_start"):
            bits.append(f"first={row['first_start']}")
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="tech_day", description="Show assignments for a technician on a specific day.")
@app_commands.describe(
    tech_id="BlueFolder technician user ID",
    when="Date in YYYY-MM-DD format",
)
async def tech_day(interaction: discord.Interaction, tech_id: int, when: str) -> None:
    await interaction.response.defer(ephemeral=True)
    day = _parse_iso_date(when)
    if not day:
        await interaction.followup.send("Use YYYY-MM-DD for the date.", ephemeral=True)
        return

    assignments = bot.bluefolder.get_assignments_for_user_day(tech_id, day)
    if not assignments:
        await interaction.followup.send(
            f"No assignments found for tech `{tech_id}` on `{when}`.",
            ephemeral=True,
        )
        return

    lines = []
    for idx, item in enumerate(assignments[:20], start=1):
        bits = [
            f"SR {item.get('service_request_id') or '?'}",
            item.get("start_display") or item.get("start") or "unscheduled",
            item.get("subject") or "Service Request",
        ]
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="who_has_sr", description="Find who has a service request in the next 14 days.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def who_has_sr(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    rows = bot.bluefolder.find_sr_assignment_window(
        sr_id,
        start_day=date.today(),
        end_day=date.today() + timedelta(days=14),
    )
    if not rows:
        await interaction.followup.send(
            f"No active-tech assignment found in the next 14 days for `{sr_id}`.",
            ephemeral=True,
        )
        return

    lines = []
    for idx, row in enumerate(rows, start=1):
        bits = [row["tech_name"]]
        if row.get("start"):
            bits.append(f"start={row['start']}")
        if row.get("end"):
            bits.append(f"end={row['end']}")
        if row.get("subject"):
            bits.append(row["subject"])
        lines.append(f"{idx}. {' | '.join(bits)}")
    await interaction.followup.send("\n".join(lines), ephemeral=True)


@bot.tree.command(name="waiver", description="Generate a prefilled waiver link for a service request.")
@app_commands.describe(sr_id="BlueFolder service request ID")
async def waiver(interaction: discord.Interaction, sr_id: int) -> None:
    await interaction.response.defer(ephemeral=True)
    result = bot.bluefolder.build_waiver_link(sr_id)
    if result.get("error"):
        await interaction.followup.send(
            f"Could not build waiver link for `{sr_id}`: {result['error']}",
            ephemeral=True,
        )
        return

    lines = [
        f"SR {result['sr_id']}",
        f"Customer: {result['customer_name']}",
        result["url"],
    ]
    await interaction.followup.send("\n".join(lines), ephemeral=True)
