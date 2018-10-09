import collections
from typing import Any

from logbook import Logger

from .pubsub import GuildDispatcher, MemberDispatcher, \
    UserDispatcher

log = Logger(__name__)


class EventDispatcher:
    """Pub/Sub routines for litecord."""
    def __init__(self, sm):
        self.state_manager = sm

        self.backends = {
            'guild': GuildDispatcher(self),
            'member': MemberDispatcher(self),
            'user': UserDispatcher(self),
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
        return await self.action(backend, 'sub', key, identifier)

    async def unsubscribe(self, backend: str, key: Any, identifier: Any):
        """Unsubscribe an element from the given backend."""
        return await self.action(backend, 'unsub', key, identifier)

    async def dispatch(self, backend_str: str, key: Any, *args, **kwargs):
        """Dispatch an event to the backend.

        The backend is responsible for everything regarding the dispatch.
        """
        backend = self.backends[backend_str]
        key = backend.KEY_TYPE(key)
        return await backend._dispatch(key, *args, **kwargs)

    async def reset(self, backend_str: str, key: Any):
        """Reset the bucket in the given backend."""
        backend = self.backends[backend_str]
        key = backend.KEY_TYPE(key)
        return await backend._reset(key)

    async def sub_many(self, backend_str: str, identifier: Any, keys: list):
        """Subscribe to many buckets inside a single backend
        at a time."""
        for key in keys:
            await self.subscribe(backend_str, key, identifier)
