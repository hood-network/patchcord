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

import asyncio


class WebsocketFileHandler:
    """A handler around a websocket that wraps normal I/O calls into
    the websocket's respective asyncio calls via asyncio.ensure_future."""

    def __init__(self, ws):
        self.ws = ws

    def write(self, data):
        """Write data into the websocket"""
        asyncio.ensure_future(self.ws.send(data))
