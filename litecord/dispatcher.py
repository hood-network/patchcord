"""

Litecord
Copyright (C) 2018-2019  Luna Mendes

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, version 3 of the License.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

from typing import List, Any, Dict

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

    async def action(self, backend_str: str, action: str, key, identifier, *args):
        """Send an action regarding a key/identifier pair to a backend.

        Action is usually "sub" or "unsub".
        """
        backend = self.backends[backend_str]
        method = getattr(backend, action)

        # convert keys to the types the backend wants
        key = backend.KEY_TYPE(key)
        identifier = backend.VAL_TYPE(identifier)

        return await method(key, identifier, *args)

    async def subscribe(self, backend: str, key: Any, identifier: Any,
                        flags: Dict[str, Any] = None):
        """Subscribe a single element to the given backend."""
        flags = flags or {}

        log.debug('SUB backend={} key={} <= id={}',
                  backend, key, identifier, backend)

        # this is a hacky solution for backwards compatibility between backends
        # that implement flags and backends that don't.

        # passing flags to backends that don't implement flags will
        # cause errors as expected.
        if flags:
            return await self.action(backend, 'sub', key, identifier, flags)

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

    async def sub_many(self, backend_str: str, identifier: Any,
                       keys: list, flags: Dict[str, Any] = None):
        """Subscribe to multiple channels (all in a single backend)
        at a time.

        Usually used when connecting to the gateway and the client
        needs to subscribe to all their guids.
        """
        flags = flags or {}
        for key in keys:
            await self.subscribe(backend_str, key, identifier, flags)

    async def mass_sub(self, identifier: Any,
                       backends: List[tuple]):
        """Mass subscribe to many backends at once."""
        for bcall in backends:
            backend_str, keys = bcall[0], bcall[1]

            if len(bcall) == 2:
                flags = {}
            elif len(bcall) == 3:
                # we have flags
                flags = bcall[2]

            log.debug('subscribing {} to {} keys in backend {}, flags: {}',
                      identifier, len(keys), backend_str, flags)

            await self.sub_many(backend_str, identifier, keys, flags)

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

    async def dispatch_filter(self, backend_str: str,
                              key: Any, func, *args):
        """Dispatch to a backend that only accepts
        (event, data) arguments with an optional filter
        function."""
        backend = self.backends[backend_str]
        key = backend.KEY_TYPE(key)
        return await backend.dispatch_filter(key, func, *args)

    async def dispatch_many_filter_list(self, backend_str: str,
                                        keys: List[Any], sess_list: List[str],
                                        *args):
        """Make a "unique" dispatch given a list of session ids.

        This only works for backends that have a dispatch_filter
        handler and return session id lists in their dispatch
        results.
        """
        for key in keys:
            sess_list.extend(
                await self.dispatch_filter(
                    backend_str, key,
                    lambda sess_id: sess_id not in sess_list,
                    *args)
            )

        return sess_list

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
