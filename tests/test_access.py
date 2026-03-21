from types import SimpleNamespace

from app.bot import client


class DummyBlueFolder:
    def __init__(self, mapped_ids=None):
        self._mapped_ids = mapped_ids or {}

    def resolve_tech_id(self, discord_user_id, candidate_names=None):
        return self._mapped_ids.get(discord_user_id)


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
    return SimpleNamespace(user=user)


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
