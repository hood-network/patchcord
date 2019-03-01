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

import urllib.parse
from litecord.voice.websocket import VoiceWebsocket


async def voice_websocket_handler(app, ws, url):
    """Main handler to instantiate a VoiceWebsocket
    with the given url."""
    args = urllib.parse.parse_qs(
        urllib.parse.urlparse(url).query
    )

    try:
        gw_version = args['v'][0]
    except (KeyError, IndexError):
        gw_version = '4'

    if gw_version not in ('1', '2', '3', '4'):
        return await ws.close(1000, 'Invalid gateway version')

    # TODO: select a different VoiceWebsocket runner depending on the selected
    # version.
    vws = VoiceWebsocket(ws, app)
    await vws.run()
