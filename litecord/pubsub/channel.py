from typing import Any
from collections import defaultdict

from logbook import Logger

from .dispatcher import DispatcherWithState

log = Logger(__name__)


class ChannelDispatcher(DispatcherWithState):
    """Main channel Pub/Sub logic."""
    KEY_TYPE = int
    VAL_TYPE = int

    async def dispatch(self, channel_id,
                       event: str, data: Any):
        """Dispatch an event to a channel."""
        user_ids = self.state[channel_id]
        dispatched = 0

        for user_id in set(user_ids):
            guild_id = await self.app.storage.guild_from_channel(channel_id)

            states = (self.sm.fetch_states(user_id, guild_id)
                      if guild_id else

                      # TODO: use a fetch_states with guild_id 0
                      # or maybe something to fetch all shards
                      # with id 0 and single shards
                      self.sm.user_states(user_id))

            dispatched += await self._dispatch_states(states, event, data)

        log.info('Dispatched chan={} {!r} to {} states',
                 channel_id, event, dispatched)
