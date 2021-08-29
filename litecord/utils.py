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
import secrets
import datetime
import re
from typing import Any, Iterable, Optional, Sequence, List, Dict, Union

from logbook import Logger
from quart.json import JSONEncoder
from quart import current_app as app

from .errors import BadRequest

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
    except Exception:
        log.exception("{} task error", name)


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
    c1 = 0xCC9E2D51
    c2 = 0x1B873593
    i = 0

    while i < bytecount:
        k1 = (
            (key[i] & 0xFF)
            | ((key[i + 1] & 0xFF) << 8)
            | ((key[i + 2] & 0xFF) << 16)
            | ((key[i + 3] & 0xFF) << 24)
        )

        i += 4

        k1 = (
            (((k1 & 0xFFFF) * c1) + ((((_u(k1) >> 16) * c1) & 0xFFFF) << 16))
        ) & 0xFFFFFFFF
        k1 = (k1 << 15) | (_u(k1) >> 17)
        k1 = (
            (((k1 & 0xFFFF) * c2) + ((((_u(k1) >> 16) * c2) & 0xFFFF) << 16))
        ) & 0xFFFFFFFF

        h1 ^= k1
        h1 = (h1 << 13) | (_u(h1) >> 19)
        h1b = (
            (((h1 & 0xFFFF) * 5) + ((((_u(h1) >> 16) * 5) & 0xFFFF) << 16))
        ) & 0xFFFFFFFF
        h1 = ((h1b & 0xFFFF) + 0x6B64) + ((((_u(h1b) >> 16) + 0xE654) & 0xFFFF) << 16)

    k1 = 0
    v = None

    if remainder == 3:
        v = (key[i + 2] & 0xFF) << 16
    elif remainder == 2:
        v = (key[i + 1] & 0xFF) << 8
    elif remainder == 1:
        v = key[i] & 0xFF

    if v is not None:
        k1 ^= v

    k1 = (((k1 & 0xFFFF) * c1) + ((((_u(k1) >> 16) * c1) & 0xFFFF) << 16)) & 0xFFFFFFFF
    k1 = (k1 << 15) | (_u(k1) >> 17)
    k1 = (((k1 & 0xFFFF) * c2) + ((((_u(k1) >> 16) * c2) & 0xFFFF) << 16)) & 0xFFFFFFFF
    h1 ^= k1

    h1 ^= len(key)

    h1 ^= _u(h1) >> 16
    h1 = (
        ((h1 & 0xFFFF) * 0x85EBCA6B) + ((((_u(h1) >> 16) * 0x85EBCA6B) & 0xFFFF) << 16)
    ) & 0xFFFFFFFF
    h1 ^= _u(h1) >> 13
    h1 = (
        (
            ((h1 & 0xFFFF) * 0xC2B2AE35)
            + ((((_u(h1) >> 16) * 0xC2B2AE35) & 0xFFFF) << 16)
        )
    ) & 0xFFFFFFFF
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
        "json",
        encoder=lambda v: json.dumps(v, cls=LitecordJSONEncoder),
        decoder=json.loads,
        schema="pg_catalog",
    )

    await con.set_type_codec(
        "jsonb",
        encoder=lambda v: json.dumps(v, cls=LitecordJSONEncoder),
        decoder=json.loads,
        schema="pg_catalog",
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
        yield input_list[idx : idx + chunk_size]


def to_update(j: dict, orig: dict, field: str) -> bool:
    """Compare values to check if j[field] is actually updating
    the value in orig[field]. Useful for icon checks."""
    return field in j and j[field] and j[field] != orig[field]


async def search_result_from_list(rows: List) -> Dict[str, Any]:
    """Generate the end result of the search query, given a list of rows.

    Each row must contain:
     - A bigint on `current_id`
     - An int (?) on `total_results`
     - Two bigint[], each on `before` and `after` respectively.
    """
    results = 0 if not rows else rows[0]["total_results"]
    res = []

    for row in rows:
        before, after = [], []

        for before_id in reversed(row["before"]):
            before.append(await app.storage.get_message(before_id))

        for after_id in row["after"]:
            after.append(await app.storage.get_message(after_id))

        msg = await app.storage.get_message(row["current_id"])
        msg["hit"] = True
        res.append(before + [msg] + after)

    return {"total_results": results, "messages": res, "analytics_id": ""}


def maybe_int(val: Any) -> Union[int, Any]:
    """Try to convert a given value to an integer. Returns the same value
    if it is not."""
    try:
        return int(val)
    except (ValueError, TypeError):
        return val


async def maybe_lazy_guild_dispatch(
    guild_id: int, event: str, role, force: bool = False
):
    # sometimes we want to dispatch an event
    # even if the role isn't hoisted

    # an example of such a case is when a role loses
    # its hoist status.

    # check if is a dict first because role_delete
    # only receives the role id.
    if isinstance(role, dict) and not role["hoist"] and not force:
        return

    await (getattr(app.lazy_guild, event))(guild_id, role)


def extract_limit(request_, default: int = 50, max_val: int = 100):
    """Extract a limit kwarg."""
    try:
        limit = int(request_.args.get("limit", default))

        if limit not in range(0, max_val + 1):
            raise ValueError()
    except (TypeError, ValueError):
        raise BadRequest("limit not int")

    return limit


def query_tuple_from_args(args: dict, limit: int) -> tuple:
    """Extract a 2-tuple out of request arguments."""
    before, after = None, None

    if "before" in args:
        before = int(args["before"])
    elif "after" in args:
        before = int(args["after"])

    return before, after


def rand_hex(length: int = 8) -> str:
    """Generate random hex characters."""
    return secrets.token_hex(length)[:length]


def parse_time(timestamp: Optional[str]) -> Optional[datetime.datetime]:
    if timestamp:
        splitted = re.split(r"[^\d]", timestamp.replace("+00:00", ""))

        # ignore last component (which can be empty, because of the last Z
        # letter in a timestamp)
        splitted = splitted[:7]
        components = list(map(int, splitted))
        return datetime.datetime(*components)

    return None


def custom_status_is_expired(expired_at: Optional[str]) -> bool:
    """Return if a custom status is expired."""
    expires_at = parse_time(expired_at)
    now = datetime.datetime.utcnow()
    return bool(expires_at and now > expires_at)


async def custom_status_set_null(user_id: int) -> None:
    """Set a user's custom status in the database to NULL.

    This function does not do any gateway side effects.
    """
    await app.db.execute(
        """
        UPDATE user_settings
        SET custom_status = NULL
        WHERE user_id = $1
        """,
        user_id,
    )


async def custom_status_to_activity(custom_status: dict) -> Optional[dict]:
    """Convert a custom status coming from user settings to an activity.

    Returns None if the given custom status is invalid and shouldn't be
    used anymore.
    """
    text = custom_status.get("text")
    emoji_id = custom_status.get("emoji_id")
    emoji_name = custom_status.get("emoji_name")
    emoji = None if emoji_id is None else await app.storage.get_emoji(emoji_id)

    activity = {"type": 4, "name": "Custom Status"}

    if emoji is not None:
        activity["emoji"] = {
            "animated": emoji["animated"],
            "id": str(emoji["id"]),
            "name": emoji["name"],
        }
    elif emoji_name is not None:
        activity["emoji"] = {"name": emoji_name}

    if text is not None:
        activity["state"] = text

    if "emoji" not in activity and "state" not in activity:
        return None

    if custom_status_is_expired(custom_status.get("expired_at")):
        return None

    return activity


def want_bytes(data: Union[str, bytes]) -> bytes:
    return data if isinstance(data, bytes) else data.encode()


def want_string(data: Union[str, bytes]) -> str:
    return data.decode() if isinstance(data, bytes) else data
