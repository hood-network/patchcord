import asyncio
from logbook import Logger

log = Logger(__name__)


async def async_map(function, iterable) -> list:
    """Map a coroutine to an iterable."""
    res = []

    for element in iterable:
        result = await function(element)
        res.append(result)

    return res


async def task_wrapper(name: str, coro):
    try:
        await coro
    except asyncio.CancelledError:
        pass
    except:
        log.exception('{} task error', name)
