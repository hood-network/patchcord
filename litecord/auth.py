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

import base64
import binascii
import asyncpg
import bcrypt
from itsdangerous import TimestampSigner, BadSignature
from logbook import Logger
from typing import overload, Optional, Literal, TYPE_CHECKING

from litecord.errors import Forbidden, Unauthorized
from litecord.enums import UserFlags

if TYPE_CHECKING:
    from litecord.typing_hax import app, request
else:
    from quart import current_app as app, request


log = Logger(__name__)


async def raw_token_check(token: str, db: Optional[asyncpg.Pool] = None) -> int:
    """Check if a given token is valid.

    Returns
    -------
    int
        The User ID of the given token.

    Raises
    ------
    Unauthorized
        If token is not properly formatted, or if the user does not exist.
    Forbidden
        If token validation fails.
    """
    db = db or app.db

    # just try by fragments instead of
    # unpacking
    fragments = token.split(".")
    user_id_str = fragments[0]

    try:
        user_id_decoded = base64.b64decode(user_id_str.encode() + b"==")
        user_id = int(user_id_decoded)
    except (ValueError, binascii.Error):
        raise Unauthorized()

    pwd_hash = await db.fetchval(
        """
        SELECT password_hash
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    if not pwd_hash:
        raise Unauthorized()

    signer = TimestampSigner(pwd_hash)

    try:
        signer.unsign(token)
        log.debug("login for uid {} successful", user_id)

        # update the user's last_session field
        # so that we can keep an exact track of activity,
        # even on long-lived single sessions (that can happen
        # with people leaving their clients open forever)
        await db.execute(
            """
            UPDATE users
            SET last_session = (now() at time zone 'utc')
            WHERE id = $1
            """,
            user_id,
        )

        return user_id
    except BadSignature:
        log.warning("Login failed for uid {}", user_id)
        raise Unauthorized()


@overload
async def token_check(to_raise: Literal[True] = ...) -> int:
    ...


@overload
async def token_check(to_raise: Literal[False] = ...) -> Optional[int]:
    ...


async def token_check(to_raise = True) -> Optional[int]:
    """Check token information."""
    # first, check if the request info already has a uid
    user_id = getattr(request, "user_id", None)
    if user_id:
        return user_id

    try:
        token = request.headers["Authorization"]
    except KeyError:
        if to_raise:
            raise Unauthorized()
        return None

    if token.startswith("Bot "):
        token = token.replace("Bot ", "")

    try:
        user_id = await raw_token_check(token)
    except Exception:
        if to_raise:
            raise
        return None

    request.user_id = user_id
    return user_id


async def admin_check() -> int:
    """Check if the user is an admin."""
    user_id = await token_check()
    if not await is_staff(user_id):
        raise Forbidden(20017)

    return user_id


async def is_staff(user_id: int) -> bool:
    """Check if the user is an admin."""
    flags = await app.db.fetchval(
        """
        SELECT flags
        FROM users
        WHERE id = $1
        """,
        user_id,
    )

    flags = UserFlags.from_int(flags)
    return flags.is_staff


async def hash_data(data: str, loop=None) -> str:
    """Hash information with bcrypt."""
    loop = loop or app.loop
    buf = data.encode()

    hashed = await loop.run_in_executor(None, bcrypt.hashpw, buf, bcrypt.gensalt(14))

    return hashed.decode()
