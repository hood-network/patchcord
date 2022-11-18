from aiohttp import ClientSession
from asyncio import AbstractEventLoop, get_event_loop
from asyncpg import Pool
from quart import current_app, Quart, Request as _Request, request
from typing import cast, Any, Optional
from winter import SnowflakeFactory
import config

from .ratelimits.bucket import RatelimitBucket
from .ratelimits.main import RatelimitManager
from .gateway.state_manager import StateManager
from .storage import Storage
from .user_storage import UserStorage
from .images import IconManager
from .dispatcher import EventDispatcher
from .presence import PresenceManager
from .guild_memory_store import GuildMemoryStore
from .pubsub.lazy_guild import LazyGuildManager
from .voice.manager import VoiceManager
from .jobs import JobManager
from .errors import BadRequest

class Request(_Request):

    discord_api_version: int
    bucket: Optional[RatelimitBucket]
    bucket_global: RatelimitBucket
    retry_after: Optional[int]
    user_id: Optional[int]
    
    def on_json_loading_failed(self, error: Exception) -> Any:
        raise BadRequest(50109)


class LitecordApp(Quart):
    request_class: Request
    session: ClientSession
    db: Pool
    sched: JobManager

    winter_factory: SnowflakeFactory
    loop: AbstractEventLoop
    ratelimiter: RatelimitManager
    state_manager: StateManager
    storage: Storage
    user_storage: UserStorage
    icons: IconManager
    dispatcher: EventDispatcher
    presence: PresenceManager
    guild_store: GuildMemoryStore
    lazy_guild: LazyGuildManager
    voice: VoiceManager

    def __init__(
        self,
        import_name: str,
        config_path: str = f"config.{config.MODE}",
    ) -> None:
        super().__init__(
            import_name,
        )
        self.config.from_object(config_path)
        self.config["MAX_CONTENT_LENGTH"] = 500 * 1024 * 1024  # 500 MB
        
    def init_managers(self):
        # Init singleton classes
        self.session = ClientSession()
        self.winter_factory = SnowflakeFactory()
        self.loop = get_event_loop()
        self.ratelimiter = RatelimitManager(self.config.get("_testing", False))
        self.state_manager = StateManager()
        self.storage = Storage(self)
        self.user_storage = UserStorage(self.storage)
        self.icons = IconManager(self)
        self.dispatcher = EventDispatcher()
        self.presence = PresenceManager(self)
        self.storage.presence = self.presence
        self.guild_store = GuildMemoryStore()
        self.lazy_guild = LazyGuildManager()
        self.voice = VoiceManager(self)
    @property
    def is_debug(self) -> bool:
        return self.config.get("DEBUG", False)


app = cast(LitecordApp, current_app)
request = cast(Request, request)
