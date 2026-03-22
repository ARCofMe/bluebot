import asyncio
from types import SimpleNamespace

import pytest

from app.bot import client
from app import main


class DummyBlueFolder:
    def __init__(self, mapped_ids=None):
        self._mapped_ids = mapped_ids or {}

    def resolve_tech_id(self, discord_user_id, candidate_names=None):
        return self._mapped_ids.get(discord_user_id)

    def get_dispatch_loads_for_day(self, day, limit=50):
        return []

    def list_active_techs(self):
        return []


class DummyResponse:
    def __init__(self):
        self.messages = []
        self.deferred = False

    async def send_message(self, content, ephemeral=False):
        self.messages.append({"content": content, "ephemeral": ephemeral})

    async def defer(self, ephemeral=False):
        self.deferred = True

    def is_done(self):
        return self.deferred or bool(self.messages)


class DummyFollowup:
    def __init__(self):
        self.messages = []

    async def send(self, content, ephemeral=False):
        self.messages.append({"content": content, "ephemeral": ephemeral})


def _interaction(*, roles=(), manage_guild=False, user_id=1, display_name="Test User", username="testuser"):
    role_objs = [SimpleNamespace(name=name) for name in roles]
    user = SimpleNamespace(
        id=user_id,
        name=username,
        display_name=display_name,
        global_name=None,
        roles=role_objs,
        guild_permissions=SimpleNamespace(manage_guild=manage_guild),
    )
    return SimpleNamespace(
        user=user,
        guild_id=123,
        guild=None,
        channel=None,
        response=DummyResponse(),
        followup=DummyFollowup(),
    )


def test_require_admin_access_allows_manage_guild(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", None)
    interaction = _interaction(manage_guild=True)
    assert client._require_admin_access(interaction) is True


def test_require_admin_access_allows_configured_admin_role(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin,Operations")
    interaction = _interaction(roles=("Operations",))
    assert client._require_admin_access(interaction) is True


def test_require_dispatch_access_inherits_admin_role(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin")
    monkeypatch.setattr(client.settings, "discord_dispatcher_role_names", "Dispatcher")
    interaction = _interaction(roles=("Admin",))
    assert client._require_dispatch_access(interaction) is True


def test_require_parts_access_inherits_dispatcher_role(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_dispatcher_role_names", "Dispatcher")
    monkeypatch.setattr(client.settings, "discord_parts_role_names", "Parts")
    interaction = _interaction(roles=("Dispatcher",))
    assert client._require_parts_access(interaction) is True


def test_help_sections_hide_admin_and_dispatch_for_plain_user(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin")
    monkeypatch.setattr(client.settings, "discord_dispatcher_role_names", "Dispatcher")
    monkeypatch.setattr(client.settings, "discord_parts_role_names", "Parts")
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder())

    sections = dict(client._help_sections(_interaction()))

    assert "Dispatch" not in sections
    assert "Parts" not in sections
    assert "Mapping And Admin" in sections
    assert not any("export_member_map" in row for row in sections["Mapping And Admin"])


def test_help_sections_show_mapped_tech_commands_for_mapped_user(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin")
    monkeypatch.setattr(client.settings, "discord_dispatcher_role_names", "Dispatcher")
    monkeypatch.setattr(client.settings, "discord_parts_role_names", "Parts")
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder(mapped_ids={42: 33538043}))

    sections = dict(client._help_sections(_interaction(user_id=42)))

    assert "Tech Schedules" in sections
    assert any("my_jobs" in row for row in sections["Tech Schedules"])
    assert "Workflow Updates" in sections
    assert any("enroute" in row for row in sections["Workflow Updates"])


def test_help_sections_show_dispatch_for_dispatcher(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin")
    monkeypatch.setattr(client.settings, "discord_dispatcher_role_names", "Dispatcher")
    monkeypatch.setattr(client.settings, "discord_parts_role_names", "Parts")
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder())

    sections = dict(client._help_sections(_interaction(roles=("Dispatcher",))))

    assert "Dispatch" in sections
    assert any("today_board" in row for row in sections["Dispatch"])


def test_command_access_policy_matches_expected_levels():
    assert client._command_access("note_add") == client.ACCESS_MAPPED_TECH
    assert client._command_access("today_board") == client.ACCESS_DISPATCH
    assert client._command_access("parts_brief") == client.ACCESS_PARTS
    assert client._command_access("lookup_member") == client.ACCESS_ADMIN
    assert client._command_access("ping") == client.ACCESS_ALL


def test_note_add_rejects_unmapped_tech(monkeypatch):
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder())
    interaction = _interaction()

    asyncio.run(client.note_add(interaction, sr_id=12345, text="Need board approval", confirm=False))

    assert interaction.response.messages
    assert "not mapped to a BlueFolder tech" in interaction.response.messages[0]["content"]


def test_note_add_preview_for_mapped_tech(monkeypatch):
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder(mapped_ids={42: 33538043}))
    interaction = _interaction(user_id=42)

    asyncio.run(client.note_add(interaction, sr_id=12345, text="Need board approval", confirm=False))

    assert interaction.response.messages
    content = interaction.response.messages[0]["content"]
    assert "Preview only: `note_add`" in content
    assert "Need board approval" in content
    assert "confirm:true" in content


def test_enroute_preview_includes_eta_when_provided(monkeypatch):
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder(mapped_ids={42: 33538043}))
    interaction = _interaction(user_id=42)

    asyncio.run(client.enroute(interaction, sr_id=12345, minutes=20, confirm=False))

    assert interaction.response.messages
    content = interaction.response.messages[0]["content"]
    assert "Preview only: `enroute`" in content
    assert "ETA: 20 minutes" in content


def test_send_response_text_splits_long_messages():
    interaction = _interaction()
    text = "\n".join(f"line {idx} {'x' * 120}" for idx in range(30))

    asyncio.run(client._send_response_text(interaction, text, ephemeral=True))

    assert len(interaction.response.messages) == 1
    assert interaction.response.messages[0]["ephemeral"] is True
    assert interaction.followup.messages
    assert all(len(message["content"]) <= client._DISCORD_MESSAGE_LIMIT for message in interaction.followup.messages)


def test_export_today_board_handles_export_write_failure(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin")
    monkeypatch.setattr(client.settings, "discord_dispatcher_role_names", "Dispatcher")
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder())
    monkeypatch.setattr(client, "_write_json_export", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Could not write export file: disk full")))
    interaction = _interaction(roles=("Dispatcher",))

    asyncio.run(client.export_today_board(interaction))

    assert interaction.response.deferred is True
    assert interaction.followup.messages
    assert interaction.followup.messages[0]["content"] == "Could not write export file: disk full"


def test_handle_app_command_error_uses_initial_response_when_not_done():
    interaction = _interaction()
    interaction.command = SimpleNamespace(name="ping")

    asyncio.run(client._handle_app_command_error(interaction, ValueError("boom")))

    assert interaction.response.messages
    assert interaction.response.messages[0]["content"] == "Unexpected error while handling that command."
    assert not interaction.followup.messages


def test_handle_app_command_error_uses_followup_after_defer():
    interaction = _interaction()
    interaction.command = SimpleNamespace(name="today_board")
    interaction.response.deferred = True

    asyncio.run(client._handle_app_command_error(interaction, RuntimeError("BlueFolder timeout")))

    assert not interaction.response.messages
    assert interaction.followup.messages
    assert interaction.followup.messages[0]["content"] == "BlueFolder timeout"


def test_setup_hook_logs_and_reraises_sync_failure(monkeypatch):
    async def boom(guild=None):
        raise RuntimeError("sync failed")

    monkeypatch.setattr(client.settings, "discord_guild_id", None)
    monkeypatch.setattr(client.bot.tree, "sync", boom)

    with pytest.raises(RuntimeError, match="sync failed"):
        asyncio.run(client.bot.setup_hook())


def test_collect_members_raises_runtime_error_when_guild_fetch_fails():
    interaction = _interaction()

    class DummyGuild:
        def fetch_members(self, limit=None):
            raise RuntimeError("forbidden")

    interaction.guild = DummyGuild()

    with pytest.raises(RuntimeError, match="Could not load Discord guild members"):
        asyncio.run(client._collect_members(interaction, scope="guild"))


def test_suggest_tech_map_handles_env_export_write_failure(monkeypatch):
    monkeypatch.setattr(client.settings, "discord_admin_role_names", "Admin")
    monkeypatch.setattr(client.bot, "bluefolder", DummyBlueFolder())
    monkeypatch.setattr(
        client,
        "_collect_members",
        lambda interaction, scope: asyncio.sleep(
            0,
            result=[{"discord_user_id": "1", "username": "testuser", "display_name": "Test User", "global_name": None, "role_names": []}],
        ),
    )
    monkeypatch.setattr(client, "_write_json_export", lambda *args, **kwargs: "/tmp/suggested.json")
    monkeypatch.setattr(
        client,
        "_write_text_export",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("Could not write export file: disk full")),
    )
    interaction = _interaction(roles=("Admin",))

    asyncio.run(client.suggest_tech_map(interaction, scope=SimpleNamespace(value="guild")))

    assert interaction.response.deferred is True
    assert interaction.followup.messages
    assert interaction.followup.messages[0]["content"] == "Could not write export file: disk full"


def test_send_channel_alert_uses_parts_label_when_channel_unavailable(monkeypatch):
    interaction = _interaction()
    monkeypatch.setattr(client.bot, "get_channel", lambda channel_id: None)

    async def fetch_channel(channel_id):
        return None

    monkeypatch.setattr(client.bot, "fetch_channel", fetch_channel)

    result = asyncio.run(
        client._send_channel_alert(
            interaction,
            title="Missing Part",
            sr_id=12345,
            note_text="Missing compressor",
            channel_id=999,
            enabled=True,
            channel_label="Parts",
        )
    )

    assert result == "Parts alert channel could not be loaded."


def test_sr_handles_bluefolder_exception_with_followup(monkeypatch):
    class FailingBlueFolder:
        def get_service_request(self, sr_id):
            raise RuntimeError("timeout")

    monkeypatch.setattr(client.bot, "bluefolder", FailingBlueFolder())
    interaction = _interaction()

    asyncio.run(client.sr(interaction, sr_id=12345))

    assert interaction.response.deferred is True
    assert interaction.followup.messages
    assert interaction.followup.messages[0]["content"] == "BlueFolder lookup failed for `12345`: timeout"


def test_missing_part_reports_logged_success_even_if_alert_fails(monkeypatch):
    class PartsBlueFolder:
        def resolve_tech_id(self, discord_user_id, candidate_names=None):
            return 33538043

        def log_parts_issue(self, sr_id, *, user_id, issue_type, details):
            return {
                "ok": True,
                "logged_at": "2026-03-21T18:00",
                "note_text": "Missing part reported at 6:00 PM. Details: compressor.",
                "customer_name": "Acme Bakery",
                "address": "123 Main St",
            }

    monkeypatch.setattr(client.bot, "bluefolder", PartsBlueFolder())

    async def fake_send_channel_alert(*args, **kwargs):
        return "Parts alert could not be sent."

    monkeypatch.setattr(client, "_send_channel_alert", fake_send_channel_alert)
    interaction = _interaction(user_id=42)

    asyncio.run(client.missing_part(interaction, sr_id=12345, details="compressor", confirm=True))

    assert interaction.response.deferred is True
    assert interaction.followup.messages
    content = interaction.followup.messages[0]["content"]
    assert "Logged missing-part issue for service request `12345`." in content
    assert "Missing part reported at 6:00 PM. Details: compressor." in content
    assert "Parts alert could not be sent." in content


def test_notes_command_splits_long_followup_output(monkeypatch):
    class NotesBlueFolder:
        def get_service_request_notes(self, sr_id):
            return [
                {
                    "dateCreated": f"2026-03-21T0{idx}:00:00",
                    "author": "Tech",
                    "entryType": "Note",
                    "text": "x" * 900,
                }
                for idx in range(4)
            ]

    monkeypatch.setattr(client.bot, "bluefolder", NotesBlueFolder())
    interaction = _interaction()

    asyncio.run(client.notes(interaction, sr_id=12345))

    assert interaction.response.deferred is True
    assert interaction.followup.messages
    assert len(interaction.followup.messages) >= 2
    assert all(len(message["content"]) <= client._DISCORD_MESSAGE_LIMIT for message in interaction.followup.messages)


def test_main_validates_settings_before_bot_run(monkeypatch):
    calls = []

    def fake_validate():
        calls.append("validate")

    def fake_run(token):
        calls.append(("run", token))

    monkeypatch.setattr(main.settings, "validate_or_raise", fake_validate)
    monkeypatch.setattr(main.settings, "discord_bot_token", "token")
    monkeypatch.setattr(main.bot, "run", fake_run, raising=False)

    main.main()

    assert calls == ["validate", ("run", "token")]
