from typing import Any

from logbook import Logger

from .dispatcher import DispatcherWithState
from litecord.permissions import get_permissions

log = Logger(__name__)


class GuildDispatcher(DispatcherWithState):
    """Guild backend for Pub/Sub"""
    KEY_TYPE = int
    VAL_TYPE = int

    async def _chan_action(self, action: str,
                           guild_id: int, user_id: int):
        """Send an action to all channels of the guild."""
        chan_ids = await self.app.storage.get_channel_ids(guild_id)

        for chan_id in chan_ids:

            # only do an action for users that can
            # actually read the channel to start with.
            chan_perms = await get_permissions(
                user_id, chan_id,
                storage=self.main_dispatcher.app.storage)

            print(user_id, chan_id, chan_perms.bits.read_messages)

            if not chan_perms.bits.read_messages:
                log.debug('skipping cid={}, no read messages',
                          chan_id)
                continue

            log.debug('sending raw action {!r} to chan={}',
                      action, chan_id)

            await self.main_dispatcher.action(
                'channel', action, chan_id, user_id
            )

    async def _chan_call(self, meth: str, guild_id: int, *args):
        """Call a method on the ChannelDispatcher, for all channels
        in the guild."""
        chan_ids = await self.app.storage.get_channel_ids(guild_id)

        chan_dispatcher = self.main_dispatcher.backends['channel']
        method = getattr(chan_dispatcher, meth)

        for chan_id in chan_ids:
            log.debug('calling {} to chan={}',
                      meth, chan_id)
            await method(chan_id, *args)

    async def sub(self, guild_id: int, user_id: int):
        """Subscribe a user to the guild."""
        await super().sub(guild_id, user_id)
        await self._chan_action('sub', guild_id, user_id)

    async def unsub(self, guild_id: int, user_id: int):
        """Unsubscribe a user from the guild."""
        await super().unsub(guild_id, user_id)
        await self._chan_action('unsub', guild_id, user_id)

    async def dispatch_filter(self, guild_id: int, func,
                              event: str, data: Any):
        """Selectively dispatch to session ids that have
        func(session_id) true."""
        user_ids = self.state[guild_id]
        dispatched = 0
        sessions = []

        # acquire a copy since we may be modifying
        # the original user_ids
        for user_id in set(user_ids):

            # fetch all states / shards that are tied to the guild.
            states = self.sm.fetch_states(user_id, guild_id)

            if not states:
                # user is actually disconnected,
                # so we should just unsub them
                await self.unsub(guild_id, user_id)
                continue

            # filter the ones that matter
            states = list(filter(
                lambda state: func(state.session_id), states
            ))

            cur_sess = await self._dispatch_states(
                states, event, data)
            sessions.extend(cur_sess)
            dispatched += len(cur_sess)

        log.info('Dispatched {} {!r} to {} states',
                 guild_id, event, dispatched)

        return sessions

    async def dispatch(self, guild_id: int,
                       event: str, data: Any):
        """Dispatch an event to all subscribers of the guild."""
        return await self.dispatch_filter(
            guild_id,
            lambda sess_id: True,
            event, data,
        )
