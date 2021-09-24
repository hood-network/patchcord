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


class OP:
    """Gateway OP codes."""

    DISPATCH = 0
    HEARTBEAT = 1
    IDENTIFY = 2
    STATUS_UPDATE = 3

    # voice connection / disconnection
    VOICE_UPDATE = 4
    VOICE_PING = 5

    RESUME = 6
    RECONNECT = 7
    REQ_GUILD_MEMBERS = 8
    INVALID_SESSION = 9

    HELLO = 10
    HEARTBEAT_ACK = 11

    # request member / presence information
    GUILD_SYNC = 12

    # request to sync up call dm / group dm
    CALL_SYNC = 13

    # request for lazy guilds
    LAZY_REQUEST = 14

    # unimplemented
    LOBBY_CONNECT = 15
    LOBBY_DISCONNECT = 16
    LOBBY_VOICE_STATES_UPDATE = 17
    STREAM_CREATE = 18
    STREAM_DELETE = 19
    STREAM_WATCH = 20
    STREAM_PING = 21
    STREAM_SET_PAUSED = 22

    # related to Slash Commands
    QUERY_APPLICATION_COMMANDS = 24
