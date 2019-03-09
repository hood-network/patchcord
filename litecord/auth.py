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

import base64
import binascii
from random import randint

import bcrypt
from asyncpg import UniqueViolationError
from itsdangerous import TimestampSigner, BadSignature
from logbook import Logger
from quart import request, current_app as app

from litecord.errors import Forbidden, Unauthorized, BadRequest
from litecord.snowflake import get_snowflake
from litecord.enums import UserFlags


log = Logger(__name__)


async def raw_token_check(token, db=None):
    db = db or app.db

    # just try by fragments instead of
    # unpacking
    fragments = token.split('.')
    user_id = fragments[0]

    try:
        user_id = base64.b64decode(user_id.encode())
        user_id = int(user_id)
    except (ValueError, binascii.Error):
        raise Unauthorized('Invalid user ID type')

    pwd_hash = await db.fetchval("""
    SELECT password_hash
    FROM users
    WHERE id = $1
    """, user_id)

    if not pwd_hash:
        raise Unauthorized('User ID not found')

    signer = TimestampSigner(pwd_hash)

    try:
        signer.unsign(token)
        log.debug('login for uid {} successful', user_id)

        # update the user's last_session field
        # so that we can keep an exact track of activity,
        # even on long-lived single sessions (that can happen
        # with people leaving their clients open forever)
        await db.execute("""
        UPDATE users
        SET last_session = (now() at time zone 'utc')
        WHERE id = $1
        """, user_id)

        return user_id
    except BadSignature:
        log.warning('token failed for uid {}', user_id)
        raise Forbidden('Invalid token')


async def token_check():
    """Check token information."""
    # first, check if the request info already has a uid
    try:
        return request.user_id
    except AttributeError:
        pass

    try:
        token = request.headers['Authorization']
    except KeyError:
        raise Unauthorized('No token provided')

    if token.startswith('Bot '):
        token = token.replace('Bot ', '')

    user_id = await raw_token_check(token)
    request.user_id = user_id
    return user_id


async def admin_check():
    """Check if the user is an admin."""
    user_id = await token_check()

    flags = await app.db.fetchval("""
    SELECT flags
    FROM users
    WHERE id = $1
    """, user_id)

    flags = UserFlags.from_int(flags)
    if not flags.is_staff:
        raise Unauthorized('you are not staff')

    return user_id


async def hash_data(data: str, loop=None) -> str:
    """Hash information with bcrypt."""
    loop = loop or app.loop
    buf = data.encode()

    hashed = await loop.run_in_executor(
        None, bcrypt.hashpw, buf, bcrypt.gensalt(14)
    )

    return hashed.decode()



async def check_username_usage(username: str, db=None):
    """Raise an error if too many people are with the same username."""
    db = db or app.db
    same_username = await db.fetchval("""
    SELECT COUNT(*)
    FROM users
    WHERE username = $1
    """, username)

    if same_username > 8000:
        raise BadRequest('Too many people.', {
            'username': 'Too many people used the same username. '
                        'Please choose another'
        })


async def create_user(username: str, email: str, password: str,
                      db=None, loop=None):
    """Create a single user."""
    db = db or app.db
    loop = loop or app.loop

    new_id = get_snowflake()

    new_discrim = randint(1, 9999)
    new_discrim = '%04d' % new_discrim

    pwd_hash = await hash_data(password, loop)

    await check_username_usage(username, db)

    try:
        await db.execute("""
        INSERT INTO users (id, email, username,
                        discriminator, password_hash)
        VALUES ($1, $2, $3, $4, $5)
        """, new_id, email, username, new_discrim, pwd_hash)
    except UniqueViolationError:
        raise BadRequest('Email already used.')

    return new_id, pwd_hash
