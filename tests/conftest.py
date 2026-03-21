import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


if "pydantic_settings" not in sys.modules:
    pydantic_settings = ModuleType("pydantic_settings")

    class SettingsConfigDict(dict):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)

    class BaseSettings:
        model_config = SettingsConfigDict()

        def __init__(self, **kwargs):
            annotations = getattr(type(self), "__annotations__", {})
            for field_name in annotations:
                if field_name in kwargs:
                    value = kwargs[field_name]
                else:
                    value = getattr(type(self), field_name, None)
                setattr(self, field_name, value)

    pydantic_settings.BaseSettings = BaseSettings
    pydantic_settings.SettingsConfigDict = SettingsConfigDict
    sys.modules["pydantic_settings"] = pydantic_settings


if "app.services.bluefolder_service" not in sys.modules:
    bluefolder_service = ModuleType("app.services.bluefolder_service")

    class BlueFolderService:
        def resolve_tech_id(self, discord_user_id, candidate_names=None):
            return None

    bluefolder_service.BlueFolderService = BlueFolderService
    sys.modules["app.services.bluefolder_service"] = bluefolder_service


if "discord" not in sys.modules:
    discord = ModuleType("discord")
    app_commands = ModuleType("discord.app_commands")
    ext = ModuleType("discord.ext")
    commands = ModuleType("discord.ext.commands")

    class _DummyTree:
        def command(self, *args, **kwargs):
            def decorator(func):
                return func
            return decorator

        def copy_global_to(self, guild=None):
            return None

        async def sync(self, guild=None):
            return []

    class _DummyBot:
        def __init__(self, *args, **kwargs):
            self.tree = _DummyTree()

        def get_channel(self, channel_id):
            return None

        async def fetch_channel(self, channel_id):
            return None

    class _Choice:
        def __init__(self, name, value):
            self.name = name
            self.value = value

    def _decorator(*args, **kwargs):
        def wrap(func):
            return func
        return wrap

    class _Intents:
        @staticmethod
        def default():
            return SimpleNamespace(members=False)

    discord.Intents = _Intents
    discord.Interaction = object
    discord.Member = object
    discord.Object = lambda id=None: SimpleNamespace(id=id)
    discord.abc = SimpleNamespace(User=object)
    app_commands.describe = _decorator
    app_commands.choices = _decorator
    app_commands.command = _decorator
    app_commands.Choice = _Choice
    commands.Bot = _DummyBot
    ext.commands = commands
    discord.app_commands = app_commands
    discord.ext = ext

    sys.modules["discord"] = discord
    sys.modules["discord.app_commands"] = app_commands
    sys.modules["discord.ext"] = ext
    sys.modules["discord.ext.commands"] = commands
