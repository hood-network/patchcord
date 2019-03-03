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

from collections import defaultdict

from logbook import Logger

from litecord.voice.lvsp_conn import LVSPConnection

log = Logger(__name__)

class LVSPManager:
    """Manager class for Litecord Voice Server Protocol (LVSP) connections.

    Spawns :class:`LVSPConnection` as needed, etc.
    """
    def __init__(self, app, voice):
        self.app = app
        self.voice = voice

        self.servers = defaultdict(dict)
        self.app.loop.create_task(self._spawn())

    async def _spawn(self):
        """Spawn LVSPConnection for each region."""

        regions = await self.app.db.fetchval("""
        SELECT id
        FROM voice_regions
        WHERE deprecated = false
        """)

        if not regions:
            log.warning('no regions are setup')
            return

        for region in regions:
            self.app.loop.create_task(
                self._spawn_region(region)
            )

    async def _spawn_region(self, region: str):
        """Spawn a region. Involves fetching all the hostnames
        for the regions and spawning a LVSPConnection for each."""
        servers = await self.app.db.fetch("""
        SELECT hostname
        FROM voice_servers
        WHERE region_id = $1
        """, region)

        if not servers:
            log.warning('region {} does not have servers', region)
            return

        servers = [r['hostname'] for r in servers]

        for hostname in servers:
            conn = LVSPConnection(self, region, hostname)
            self.servers[region][hostname] = conn

            self.app.loop.create_task(
                conn.run()
            )

    async def del_conn(self, conn):
        """Delete a connection from the connection pool."""
        try:
            self.servers[conn.region].pop(conn.hostname)
        except KeyError:
            pass
