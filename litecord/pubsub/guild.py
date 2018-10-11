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

    async def _chan_action(self, action: str, guild_id: int, user_id: int):
        chan_ids = await self.app.storage.get_channel_ids(guild_id)

        # TODO: check READ_MESSAGE permissions for the user

        for chan_id in chan_ids:
            log.debug('sending raw action {!r} to chan={}',
                      action, chan_id)

            await self.main_dispatcher.action(
                'channel', action, chan_id, user_id
            )

    async def _chan_call(self, meth: str, guild_id: int, *args):
        chan_ids = await self.app.storage.get_channel_ids(guild_id)
        chan_dispatcher = self.main_dispatcher.backends['channel']
        method = getattr(chan_dispatcher, meth)

        for chan_id in chan_ids:
            log.debug('calling {} to chan={}',
                      meth, chan_id)
            await method(chan_id, *args)

    async def sub(self, guild_id: int, user_id: int):
        self.guild_buckets[guild_id].add(user_id)

        # when subbing a user to the guild, we should sub them
        # to every channel they have access to, in the guild.

        await self._chan_action('sub', guild_id, user_id)

    async def unsub(self, guild_id: int, user_id: int):
        self.guild_buckets[guild_id].discard(user_id)
        await self._chan_action('unsub', guild_id, user_id)

    async def reset(self, guild_id: int):
        self.guild_buckets[guild_id] = set()
        await self._chan_call(guild_id, 'reset')

    async def remove(self, guild_id: int):
        try:
            self.guild_buckets.pop(guild_id)
        except KeyError:
            pass

        await self._chan_call(guild_id, 'remove')

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
                # so we should just unsub them
                await self.unsub(guild_id, user_id)
                continue

            dispatched += await self._dispatch_states(
                states, event_name, event_payload)

        log.info('Dispatched {} {!r} to {} states',
                 guild_id, event_name, dispatched)
