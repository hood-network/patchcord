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

class VoiceOP:
    identify = 0
    select_protocol = 1
    ready = 2
    heartbeat = 3
    session_description = 4
    speaking = 5
    heartbeat_ack = 6
    resume = 7
    hello = 8
    resumed = 9
    client_connect = 12
    client_disconnect = 13
