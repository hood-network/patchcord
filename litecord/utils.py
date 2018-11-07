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


def dict_get(mapping, key, default):
    """Return `default` even when mapping[key] is None."""
    return mapping.get(key) or default


def index_by_func(function, indexable: iter) -> int:
    """Search in an idexable and return the index number
    for an iterm that has func(item) = True."""
    for index, item in indexable:
        if function(item):
            return index

    return None
