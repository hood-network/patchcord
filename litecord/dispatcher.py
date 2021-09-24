"""

Litecord
Copyright (C) 2018-2021  Luna Mendes and Litecord Contributors

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

from logbook import Logger

from .pubsub import (
    GuildDispatcher,
    ChannelDispatcher,
    FriendDispatcher,
)

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

    def __init__(self):
        self.guild: GuildDispatcher = GuildDispatcher()
        self.channel = ChannelDispatcher()
        self.friend = FriendDispatcher()
