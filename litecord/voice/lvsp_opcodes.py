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


class OPCodes:
    """LVSP OP codes."""

    hello = 0
    identify = 1
    resume = 2
    ready = 3
    heartbeat = 4
    heartbeat_ack = 5
    info = 6


InfoTable = {
    "CHANNEL_REQ": 0,
    "CHANNEL_ASSIGN": 1,
    "CHANNEL_UPDATE": 2,
    "CHANNEL_DESTROY": 3,
    "VST_CREATE": 4,
    "VST_UPDATE": 5,
    "VST_LEAVE": 6,
}

InfoReverse = {v: k for k, v in InfoTable.items()}
