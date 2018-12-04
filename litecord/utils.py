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
    for index, item in enumerate(indexable):
        if function(item):
            return index

    return None


def _u(val):
    """convert to unsigned."""
    return val % 0x100000000


def mmh3(key: str, seed: int = 0):
    """MurMurHash3 implementation.

    This seems to match Discord's JavaScript implementaiton.

    Based off
      https://github.com/garycourt/murmurhash-js/blob/master/murmurhash3_gc.js
    """
    key = [ord(c) for c in key]

    remainder = len(key) & 3
    bytecount = len(key) - remainder
    h1 = seed

    # mm3 constants
    c1 = 0xcc9e2d51
    c2 = 0x1b873593
    i = 0

    while i < bytecount:
        k1 = (
            (key[i] & 0xff) |
            ((key[i + 1] & 0xff) << 8) |
            ((key[i + 2] & 0xff) << 16) |
            ((key[i + 3] & 0xff) << 24)
        )

        i += 4

        k1 = ((((k1 & 0xffff) * c1) + ((((_u(k1) >> 16) * c1) & 0xffff) << 16))) & 0xffffffff
        k1 = (k1 << 15) | (_u(k1) >> 17)
        k1 = ((((k1 & 0xffff) * c2) + ((((_u(k1) >> 16) * c2) & 0xffff) << 16))) & 0xffffffff;

        h1 ^= k1
        h1 = (h1 << 13) | (_u(h1) >> 19);
        h1b = ((((h1 & 0xffff) * 5) + ((((_u(h1) >> 16) * 5) & 0xffff) << 16))) & 0xffffffff;
        h1 = (((h1b & 0xffff) + 0x6b64) + ((((_u(h1b) >> 16) + 0xe654) & 0xffff) << 16))


    k1 = 0
    v = None

    if remainder == 3:
        v = (key[i + 2] & 0xff) << 16
    elif remainder == 2:
        v = (key[i + 1] & 0xff) << 8
    elif remainder == 1:
        v = (key[i] & 0xff)

    if v is not None:
        k1 ^= v

    k1 = (((k1 & 0xffff) * c1) + ((((_u(k1) >> 16) * c1) & 0xffff) << 16)) & 0xffffffff
    k1 = (k1 << 15) | (_u(k1) >> 17)
    k1 = (((k1 & 0xffff) * c2) + ((((_u(k1) >> 16) * c2) & 0xffff) << 16)) & 0xffffffff
    h1 ^= k1

    h1 ^= len(key)

    h1 ^= _u(h1) >> 16
    h1 = (((h1 & 0xffff) * 0x85ebca6b) + ((((_u(h1) >> 16) * 0x85ebca6b) & 0xffff) << 16)) & 0xffffffff
    h1 ^= _u(h1) >> 13
    h1 = ((((h1 & 0xffff) * 0xc2b2ae35) + ((((_u(h1) >> 16) * 0xc2b2ae35) & 0xffff) << 16))) & 0xffffffff
    h1 ^= _u(h1) >> 16

    return _u(h1) >> 0
