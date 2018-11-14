import asyncio


class JobManager:
    """Manage background jobs"""
    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.jobs = []

    def spawn(self, coro):
        task = self.loop.create_task(coro)
        self.jobs.append(task)

    def close(self):
        for job in self.jobs:
            job.cancel()
