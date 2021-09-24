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
from typing import Any

from logbook import Logger

log = Logger(__name__)


class EmptyContext:
    async def __aenter__(self):
        pass

    async def __aexit__(self, _typ, _value, _traceback):
        pass


class JobManager:
    """Background job manager.

    Handles closing all existing jobs when going on a shutdown. This does not
    use helpers such as asyncio.gather and asyncio.Task.all_tasks. It only uses
    its own internal list of jobs.
    """

    def __init__(self, *, loop=None, context_func=None):
        self.loop = loop or asyncio.get_event_loop()
        self.context_function = context_func or EmptyContext
        self.jobs = []

    async def _wrapper(self, coro):
        """Wrapper coroutine for other coroutines. This adds a simple
        try/except for general exceptions to be logged.
        """
        try:
            await coro
        except Exception:
            log.exception("Error while running job")

    def spawn(self, coro):
        """Spawn a given future or coroutine in the background."""

        async def _ctx_wrapper_bg() -> Any:
            async with self.context_function():
                return await coro

        task = self.loop.create_task(self._wrapper(_ctx_wrapper_bg()))
        self.jobs.append(task)
        return task

    def close(self):
        """Close the job manager, cancelling all existing jobs.

        It is the job's responsibility to handle the given CancelledError
        and release any acquired resources.
        """
        for job in self.jobs:
            job.cancel()
