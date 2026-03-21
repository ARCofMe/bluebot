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


if "requests" not in sys.modules:
    sys.modules["requests"] = ModuleType("requests")


if "bluefolder_api" not in sys.modules:
    bluefolder_api = ModuleType("bluefolder_api")
    bluefolder_api_client = ModuleType("bluefolder_api.client")

    class BlueFolderClient:
        def __init__(self, **kwargs):
            self.users = SimpleNamespace(
                list_active=lambda: [],
                list_all=lambda: [],
                get_by_id=lambda user_id: None,
            )
            self.assignments = SimpleNamespace(
                list_for_user_range=lambda *args, **kwargs: [],
            )
            self.service_requests = SimpleNamespace(
                get_by_id=lambda sr_id: SimpleNamespace(find=lambda pattern: None),
                get_history=lambda sr_id: SimpleNamespace(findall=lambda pattern: []),
                edit_assignment=lambda *args, **kwargs: SimpleNamespace(attrib={}, findtext=lambda pattern: None),
                complete_assignment=lambda *args, **kwargs: SimpleNamespace(attrib={}, findtext=lambda pattern: None),
                add_comment=lambda *args, **kwargs: SimpleNamespace(attrib={}, findtext=lambda pattern: None),
            )
            self.customers = SimpleNamespace(
                list=lambda: SimpleNamespace(findall=lambda pattern: []),
                get_by_id=lambda customer_id: SimpleNamespace(find=lambda pattern: None),
            )
            self.customer_contacts = SimpleNamespace(
                list_for_customer=lambda customer_id: [],
            )
            self.attachments = SimpleNamespace(
                list_for_service_request=lambda sr_id: [],
            )
            self.equipment = SimpleNamespace(
                list_for_customer=lambda customer_id: [],
            )

    bluefolder_api_client.BlueFolderClient = BlueFolderClient
    bluefolder_api.client = bluefolder_api_client
    sys.modules["bluefolder_api"] = bluefolder_api
    sys.modules["bluefolder_api.client"] = bluefolder_api_client


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
