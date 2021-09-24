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

import urllib.parse
from typing import Optional
from litecord.gateway.websocket import GatewayWebsocket


async def websocket_handler(app, ws, url):
    """Main websocket handler, checks query arguments when connecting to
    the gateway and spawns a GatewayWebsocket instance for the connection."""
    args = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)

    # pull a dict.get but in a really bad way.
    try:
        gw_version = args["v"][0]
    except (KeyError, IndexError):
        gw_version = "6"

    try:
        gw_encoding = args["encoding"][0]
    except (KeyError, IndexError):
        gw_encoding = "json"

    if gw_version not in ("6", "7", "8", "9"):
        return await ws.close(4000, f"Invalid gateway version (got {gw_version})")

    if gw_encoding not in ("json", "etf"):
        return await ws.close(4000, f"Invalid gateway encoding (got {gw_encoding})")

    try:
        gw_compress: Optional[str] = args["compress"][0]
    except (KeyError, IndexError):
        gw_compress = None

    if gw_compress and gw_compress not in ("zlib-stream", "zstd-stream"):
        return await ws.close(1000, "Invalid gateway compress")

    async with app.app_context():
        gws = GatewayWebsocket(
            ws,
            version=int(gw_version),
            encoding=gw_encoding or "json",
            compress=gw_compress,
        )

        # this can be run with a single await since this whole coroutine
        # is already running in the background.
        await gws.run()
