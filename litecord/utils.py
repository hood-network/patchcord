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
import json
from typing import Any, Iterable, Optional, Sequence

from logbook import Logger
from quart.json import JSONEncoder

log = Logger(__name__)


async def async_map(function, iterable: Iterable) -> list:
    """Map a coroutine to an iterable."""
    res = []

    for element in iterable:
        result = await function(element)
        res.append(result)

    return res


async def task_wrapper(name: str, coro):
    """Wrap a given coroutine in a task."""
    try:
        await coro
    except asyncio.CancelledError:
        pass
    except:
        log.exception('{} task error', name)


def dict_get(mapping, key, default):
    """Return `default` even when mapping[key] is None."""
    return mapping.get(key) or default


def index_by_func(function, indexable: Sequence[Any]) -> Optional[int]:
    """Search in an idexable and return the index number
    for an iterm that has func(item) = True."""
    for index, item in enumerate(indexable):
        if function(item):
            return index

    return None


def _u(val):
    """convert to unsigned."""
    return val % 0x100000000


def mmh3(inp_str: str, seed: int = 0):
    """MurMurHash3 implementation.

    This seems to match Discord's JavaScript implementaiton.

    Based off
      https://github.com/garycourt/murmurhash-js/blob/master/murmurhash3_gc.js
    """
    key = [ord(c) for c in inp_str]

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


class LitecordJSONEncoder(JSONEncoder):
    """Custom JSON encoder for Litecord."""
    def default(self, value: Any):
        """By default, this will try to get the to_json attribute of a given
        value being JSON encoded."""
        try:
            return value.to_json
        except AttributeError:
            return super().default(value)


async def pg_set_json(con):
    """Set JSON and JSONB codecs for an asyncpg connection."""
    await con.set_type_codec(
        'json',
        encoder=lambda v: json.dumps(v, cls=LitecordJSONEncoder),
        decoder=json.loads,
        schema='pg_catalog'
    )

    await con.set_type_codec(
        'jsonb',
        encoder=lambda v: json.dumps(v, cls=LitecordJSONEncoder),
        decoder=json.loads,
        schema='pg_catalog'
    )


def yield_chunks(input_list: Sequence[Any], chunk_size: int):
    """Yield successive n-sized chunks from l.

    Taken from https://stackoverflow.com/a/312464.

    Modified to make linter happy (variable name changes,
    typing, comments).
    """

    # range accepts step param, so we use that to
    # make the chunks
    for idx in range(0, len(input_list), chunk_size):
        yield input_list[idx:idx + chunk_size]

def to_update(j: dict, orig: dict, field: str) -> bool:
    """Compare values to check if j[field] is actually updating
    the value in orig[field]. Useful for icon checks."""
    return field in j and j[field] and j[field] != orig[field]
