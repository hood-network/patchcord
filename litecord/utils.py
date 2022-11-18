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
import secrets
import datetime
import re
from typing import Any, Iterable, Optional, Sequence, Union, TypeVar, TYPE_CHECKING

from logbook import Logger

from .errors import ManualFormError
from .enums import Flags

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request

log = Logger(__name__)

EPOCH = 1420070400000
TF = TypeVar("TF", bound=Flags)


async def async_map(function, iterable: Iterable) -> list:
    """Map a coroutine to an iterable."""
    return await asyncio.gather(*(function(item) for item in iterable))


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
    return field in j and j[field] != orig[field]


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

    kwargs = {}
    if event == "role_delete":
        kwargs = {"deleted": True}

    await (getattr(app.lazy_guild, event))(guild_id, role, **kwargs)


def extract_limit(request_, min_val: int = 1, default: int = 50, max_val: int = 100):
    """Extract a limit kwarg."""
    try:
        limit = int(request_.args.get("limit", default))
    except (TypeError, ValueError):
        raise ManualFormError(
            limit={
                "code": "NUMBER_TYPE_COERCE",
                "message": f"Value \"{request_.args['limit']}\" is not int.",
            }
        )

    if limit < min_val:
        raise ManualFormError(
            limit={
                "code": "NUMBER_TYPE_MIN",
                "message": f"Value should be greater than or equal to 0.",
            }
        )
    if limit > max_val:
        raise ManualFormError(
            limit={
                "code": "NUMBER_TYPE_MAX",
                "message": f"Value should be less than or equal to {max_val}.",
            }
        )

    return limit


def query_tuple_from_args(args: dict, limit: int) -> tuple:
    """Extract a 2-tuple out of request arguments."""
    before, after = None, None

    if "before" in args:
        before = int(args["before"])
    elif "after" in args:
        after = int(args["after"])

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


def snowflake_timestamp(id: int) -> datetime.datetime:
    timestamp = ((id >> 22) + EPOCH) / 1000
    return datetime.datetime.fromtimestamp(timestamp, tz=datetime.timezone.utc)


def toggle_flag(flags: TF, value: int, state: bool) -> TF:
    if state is True:
        flags.value |= value
    elif state is False:
        flags.value &= ~value

    return flags


def str_bool(val: Union[str, bool]) -> Optional[bool]:
    if isinstance(val, bool):
        return val
    elif val.lower() in ("true", "1"):
        return True
    elif val.lower() in ("false", "0"):
        return False
    else:
        return None
