import collections
from typing import List, Any

from logbook import Logger

from .pubsub import GuildDispatcher, MemberDispatcher, \
    UserDispatcher, ChannelDispatcher, FriendDispatcher, \
    LazyGuildDispatcher

log = Logger(__name__)


class EventDispatcher:
    """Pub/Sub routines for litecord.

    EventDispatcher is the middle man between
    REST code and gateway event logic.

    It sets up Pub/Sub backends and each of them
    have their own ways of dispatching a single event.

    "key" and "identifier" are the "channel" and "subscriber id"
    of pub/sub. clients can subscribe to a channel using its backend
    and the key inside the backend.

    when dispatching, the backend can do its own logic, given
    its subscriber ids.
    """
    def __init__(self, app):
        self.state_manager = app.state_manager
        self.app = app

        self.backends = {
            'guild': GuildDispatcher(self),
            'member': MemberDispatcher(self),
            'channel': ChannelDispatcher(self),
            'user': UserDispatcher(self),
            'friend': FriendDispatcher(self),
            'lazy_guild': LazyGuildDispatcher(self),
        }

    async def action(self, backend_str: str, action: str, key, identifier):
        """Send an action regarding a key/identifier pair to a backend.

        Action is usually "sub" or "unsub".
        """
        backend = self.backends[backend_str]
        method = getattr(backend, action)

        # convert keys to the types the backend wants
        key = backend.KEY_TYPE(key)
        identifier = backend.VAL_TYPE(identifier)

        return await method(key, identifier)

    async def subscribe(self, backend: str, key: Any, identifier: Any):
        """Subscribe a single element to the given backend."""
        log.debug('SUB backend={} key={} <= id={}',
                  backend, key, identifier, backend)

        return await self.action(backend, 'sub', key, identifier)

    async def unsubscribe(self, backend: str, key: Any, identifier: Any):
        """Unsubscribe an element from the given backend."""
        log.debug('UNSUB backend={} key={} => id={}',
                  backend, key, identifier, backend)

        return await self.action(backend, 'unsub', key, identifier)

    async def sub(self, backend, key, identifier):
        """Alias to subscribe()."""
        return await self.subscribe(backend, key, identifier)

    async def unsub(self, backend, key, identifier):
        """Alias to unsubscribe()."""
        return await self.unsubscribe(backend, key, identifier)

    async def sub_many(self, backend_str: str, identifier: Any, keys: list):
        """Subscribe to multiple channels (all in a single backend)
        at a time.

        Usually used when connecting to the gateway and the client
        needs to subscribe to all their guids.
        """
        for key in keys:
            await self.subscribe(backend_str, key, identifier)

    async def dispatch(self, backend_str: str, key: Any, *args, **kwargs):
        """Dispatch an event to the backend.

        The backend is responsible for everything regarding the
        actual dispatch.
        """
        backend = self.backends[backend_str]

        # convert types
        key = backend.KEY_TYPE(key)
        return await backend.dispatch(key, *args, **kwargs)

    async def dispatch_many(self, backend_str: str,
                            keys: List[Any], *args, **kwargs):
        """Dispatch to multiple keys in a single backend."""
        log.info('MULTI DISPATCH: {!r}, {} keys',
                 backend_str, len(keys))

        for key in keys:
            await self.dispatch(backend_str, key, *args, **kwargs)

    async def reset(self, backend_str: str, key: Any):
        """Reset the bucket in the given backend."""
        backend = self.backends[backend_str]
        key = backend.KEY_TYPE(key)
        return await backend.reset(key)

    async def remove(self, backend_str: str, key: Any):
        """Remove a key from the backend. This
        might be a different operation than resetting."""
        backend = self.backends[backend_str]
        key = backend.KEY_TYPE(key)
        return await backend.remove(key)

    async def dispatch_guild(self, guild_id, event, data):
        """Backwards compatibility with old EventDispatcher."""
        return await self.dispatch('guild', guild_id, event, data)

    async def dispatch_user_guild(self, user_id, guild_id, event, data):
        """Backwards compatibility with old EventDispatcher."""
        return await self.dispatch('member', (guild_id, user_id), event, data)

    async def dispatch_user(self, user_id, event, data):
        """Backwards compatibility with old EventDispatcher."""
        return await self.dispatch('user', user_id, event, data)
