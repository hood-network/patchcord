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

from typing import Any

from logbook import Logger

from .dispatcher import DispatcherWithFlags
from litecord.permissions import get_permissions

log = Logger(__name__)


class GuildDispatcher(DispatcherWithFlags):
    """Guild backend for Pub/Sub"""
    KEY_TYPE = int
    VAL_TYPE = int

    async def _chan_action(self, action: str,
                           guild_id: int, user_id: int, flags=None):
        """Send an action to all channels of the guild."""
        flags = flags or {}
        chan_ids = await self.app.storage.get_channel_ids(guild_id)

        for chan_id in chan_ids:

            # only do an action for users that can
            # actually read the channel to start with.
            chan_perms = await get_permissions(
                user_id, chan_id,
                storage=self.main_dispatcher.app.storage)

            if not chan_perms.bits.read_messages:
                log.debug('skipping cid={}, no read messages',
                          chan_id)
                continue

            log.debug('sending raw action {!r} to chan={}',
                      action, chan_id)

            # for now, only sub() has support for flags.
            # it is an idea to have flags support for other actions
            args = []
            if action == 'sub':
                chanflags = dict(flags)

                # channels don't need presence flags
                try:
                    chanflags.pop('presence')
                except KeyError:
                    pass

                args.append(chanflags)

            await self.main_dispatcher.action(
                'channel', action, chan_id, user_id, *args
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

    async def sub(self, guild_id: int, user_id: int, flags=None):
        """Subscribe a user to the guild."""
        await super().sub(guild_id, user_id, flags)
        await self._chan_action('sub', guild_id, user_id, flags)

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

            # skip the given subscriber if event starts with PRESENCE_
            # and the flags say they don't want it.

            # note that this does not equate to any unsubscription
            # of the channel.
            if event.startswith('PRESENCE_') and \
                    not self.flags_get(guild_id, user_id, 'presence', True):
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
