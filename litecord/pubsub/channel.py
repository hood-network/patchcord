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

from typing import Any, List

from logbook import Logger

from .dispatcher import DispatcherWithState
from litecord.enums import ChannelType
from litecord.utils import index_by_func

log = Logger(__name__)


def gdm_recipient_view(orig: dict, user_id: int) -> dict:
    """Create a copy of the original channel object that doesn't
    show the user we are dispatching it to.

    this only applies to group dms and discords' api design that says
    a group dms' recipients must not show the original user.
    """
    # make a copy or the original channel object
    data = dict(orig)

    idx = index_by_func(
        lambda user: user['id'] == str(user_id),
        data['recipients']
    )

    data['recipients'].pop(idx)

    return data


class ChannelDispatcher(DispatcherWithFlags):
    """Main channel Pub/Sub logic."""
    KEY_TYPE = int
    VAL_TYPE = int

    async def dispatch(self, channel_id,
                       event: str, data: Any) -> List[str]:
        """Dispatch an event to a channel."""
        # get everyone who is subscribed
        # and store the number of states we dispatched the event to
        user_ids = self.state[channel_id]
        dispatched = 0
        sessions: List[str] = []

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

            # skip typing events for users that don't want it
            if event.startswith('TYPING_') and \
                    not self.flags_get(channel_id, user_id, 'typing', True):
                continue

            cur_sess = []

            if event in ('CHANNEL_CREATE', 'CHANNEL_UPDATE') \
                and data.get('type') == ChannelType.GROUP_DM.value:
                # we edit the channel payload so it doesn't show
                # the user as a recipient

                new_data = gdm_recipient_view(data, user_id)
                cur_sess = await self._dispatch_states(
                    states, event, new_data)
            else:
                cur_sess = await self._dispatch_states(
                    states, event, data)

            sessions.extend(cur_sess)
            dispatched += len(cur_sess)

        log.info('Dispatched chan={} {!r} to {} states',
                 channel_id, event, dispatched)

        return sessions
