from typing import Any
from collections import defaultdict

from logbook import Logger

from .dispatcher import Dispatcher

log = Logger(__name__)


class ChannelDispatcher(Dispatcher):
    """Main channel Pub/Sub logic."""
    def __init__(self, main):
        super().__init__(main)

        self.channels = defaultdict(set)

    async def sub(self, channel_id: int, user_id: int):
        self.channels[channel_id].add(user_id)

    async def unsub(self, channel_id: int, user_id: int):
        self.channels[channel_id].discard(user_id)

    async def reset(self, channel_id: int):
        self.channels[channel_id] = set()

    async def remove(self, channel_id: int):
        try:
            self.channels.pop(channel_id)
        except KeyError:
            pass

    async def dispatch(self, channel_id,
                       event: str, data: Any):
        user_ids = self.channels[channel_id]
        dispatched = 0

        for user_id in set(user_ids):
            guild_id = await self.app.storage.guild_from_channel(channel_id)

            if guild_id:
                states = self.sm.fetch_states(user_id, guild_id)
            else:
                # TODO: maybe a fetch_states with guild_id 0
                # to get the shards with id 0 AND the single shards?
                states = self.sm.user_states(user_id)

            dispatched += await self._dispatch_states(states, event, data)

        log.info('Dispatched chan={} {!r} to {} states',
                 channel_id, event, dispatched)
