from typing import Any

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
        # get everyone who is subscribed
        # and store the number of states we dispatched the event to
        user_ids = self.state[channel_id]
        dispatched = 0

        # making a copy of user_ids since
        # we'll modify it later on.
        for user_id in set(user_ids):
            guild_id = await self.app.storage.guild_from_channel(channel_id)

            # if we are dispatching to a guild channel,
            # we should only dispatch to the states / shards
            # that are connected to the guild (via their shard id).
            
            # if we aren't, we just get all states tied to the user.
            # TODO: make a fetch_states that fetches shards
            #        - with id 0 (count any) OR
            #        - single shards (id=0, count=1)
            states = (self.sm.fetch_states(user_id, guild_id)
                      if guild_id else
                      self.sm.user_states(user_id))

            # unsub people who don't have any states tied to the channel.
            if not states:
                await self.unsub(channel_id, user_id)
                continue

            dispatched += await self._dispatch_states(states, event, data)

        log.info('Dispatched chan={} {!r} to {} states',
                 channel_id, event, dispatched)
