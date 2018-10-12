import collections
from typing import Any

from logbook import Logger

from .pubsub import GuildDispatcher, MemberDispatcher, \
    UserDispatcher, ChannelDispatcher

log = Logger(__name__)


class EventDispatcher:
    """Pub/Sub routines for litecord."""
    def __init__(self, app):
        self.state_manager = app.state_manager
        self.app = app

        self.backends = {
            'guild': GuildDispatcher(self),
            'member': MemberDispatcher(self),
            'channel': ChannelDispatcher(self),
            'user': UserDispatcher(self),

            # TODO: channel, friends
        }

    async def action(self, backend_str: str, action: str, key, identifier):
        """Send an action regarding a key/identifier pair to a backend."""
        backend = self.backends[backend_str]
        method = getattr(backend, f'{action}')

        key = backend.KEY_TYPE(key)
        identifier = backend.VAL_TYPE(identifier)

        return await method(key, identifier)

    async def subscribe(self, backend: str, key: Any, identifier: Any):
        """Subscribe a single element to the given backend."""
        log.debug('SUB bacjend={} key={} <= id={}',
                  backend, key, identifier, backend)
        return await self.action(backend, 'sub', key, identifier)

    async def unsubscribe(self, backend: str, key: Any, identifier: Any):
        """Unsubscribe an element from the given backend."""
        log.debug('UNSUB bacjend={} key={} => id={}',
                  backend, key, identifier, backend)
        return await self.action(backend, 'unsub', key, identifier)

    async def sub(self, backend, key, identifier):
        return await self.subscribe(backend, key, identifier)

    async def unsub(self, backend, key, identifier):
        return await self.unsubscribe(backend, key, identifier)

    async def dispatch(self, backend_str: str, key: Any, *args, **kwargs):
        """Dispatch an event to the backend.

        The backend is responsible for everything regarding the dispatch.
        """
        backend = self.backends[backend_str]
        key = backend.KEY_TYPE(key)
        return await backend.dispatch(key, *args, **kwargs)

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

    async def sub_many(self, backend_str: str, identifier: Any, keys: list):
        """Subscribe to many buckets inside a single backend
        at a time."""
        for key in keys:
            await self.subscribe(backend_str, key, identifier)

    async def dispatch_guild(self, guild_id, event, data):
        """Backwards compatibility."""
        return await self.dispatch('guild', guild_id, event, data)

    async def dispatch_user_guild(self, user_id, guild_id, event, data):
        """Backwards compatibility."""
        return await self.dispatch('member', (guild_id, user_id), event, data)

    async def dispatch_user(self, user_id, event, data):
        """Backwards compatibility."""
        return await self.dispatch('user', user_id, event, data)
