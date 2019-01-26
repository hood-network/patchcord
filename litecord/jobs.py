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

import asyncio

from logbook import Logger
log = Logger(__name__)


class JobManager:
    """Manage background jobs"""
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.jobs = []

    async def _wrapper(self, coro):
        try:
            await coro
        except Exception:
            log.exception('Error while running job')

    def spawn(self, coro):
        task = self.loop.create_task(
            self._wrapper(coro)
        )

        self.jobs.append(task)

    def close(self):
        for job in self.jobs:
            job.cancel()
