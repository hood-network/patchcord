from collections import defaultdict
from typing import Any

from logbook import Logger

from .dispatcher import Dispatcher

log = Logger(__name__)


class GuildDispatcher(Dispatcher):
    """Guild backend for Pub/Sub"""
    KEY_TYPE = int
    VAL_TYPE = int

    def __init__(self, main):
        super().__init__(main)
        self.guild_buckets = defaultdict(set)

    async def sub(self, guild_id: int, user_id: int):
        self.guild_buckets[guild_id].add(user_id)

    async def unsub(self, guild_id: int, user_id: int):
        self.guild_buckets[guild_id].discard(user_id)

    async def reset(self, guild_id: int):
        self.guild_buckets[guild_id] = set()

    async def remove(self, guild_id: int):
        try:
            self.guild_buckets.pop(guild_id)
        except KeyError:
            pass

    async def dispatch(self, guild_id: int,
                       event_name: str, event_payload: Any):
        user_ids = self.guild_buckets[guild_id]
        dispatched = 0

        # acquire a copy since we will be modifying
        # the original user_ids
        for user_id in set(user_ids):

            # fetch all states related to the user id and guild id.
            states = self.sm.fetch_states(user_id, guild_id)

            if not states:
                # user is actually disconnected,
                # so we should just unsub it
                await self.unsub(guild_id, user_id)
                continue

            dispatched += await self._dispatch_states(
                states, event_name, event_payload)

        log.info('Dispatched {} {!r} to {} states',
                 guild_id, event_name, dispatched)
