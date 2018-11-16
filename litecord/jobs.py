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
