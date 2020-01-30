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

from random import randint
from typing import Tuple, Optional

from quart import current_app as app
from asyncpg import UniqueViolationError
from logbook import Logger

from ..presence import BasePresence
from ..snowflake import get_snowflake
from ..errors import BadRequest
from ..auth import hash_data
from ..utils import rand_hex

log = Logger(__name__)


async def mass_user_update(user_id):
    """Dispatch USER_UPDATE in a mass way."""
    # by using dispatch_with_filter
    # we're guaranteeing all shards will get
    # a USER_UPDATE once and not any others.

    session_ids = []

    public_user = await app.storage.get_user(user_id)
    private_user = await app.storage.get_user(user_id, secure=True)

    session_ids.extend(
        await app.dispatcher.dispatch_user(user_id, "USER_UPDATE", private_user)
    )

    guild_ids = await app.user_storage.get_user_guilds(user_id)
    friend_ids = await app.user_storage.get_friend_ids(user_id)

    session_ids.extend(
        await app.dispatcher.dispatch_many_filter_list(
            "guild", guild_ids, session_ids, "USER_UPDATE", public_user
        )
    )

    session_ids.extend(
        await app.dispatcher.dispatch_many_filter_list(
            "friend", friend_ids, session_ids, "USER_UPDATE", public_user
        )
    )

    await app.dispatcher.dispatch_many("lazy_guild", guild_ids, "update_user", user_id)

    return public_user, private_user


async def check_username_usage(username: str):
    """Raise an error if too many people are with the same username."""
    same_username = await app.db.fetchval(
        """
        SELECT COUNT(*)
        FROM users
        WHERE username = $1
        """,
        username,
    )

    if same_username > 9000:
        raise BadRequest(
            "Too many people.",
            {
                "username": "Too many people used the same username. "
                "Please choose another"
            },
        )


def _raw_discrim() -> str:
    discrim_number = randint(1, 9999)
    return "%04d" % discrim_number


async def roll_discrim(username: str) -> Optional[str]:
    """Roll a discriminator for a DiscordTag.

    Tries to generate one 10 times.

    Calls check_username_usage.
    """

    # we shouldn't roll discrims for usernames
    # that have been used too much.
    await check_username_usage(username)

    # max 10 times for a reroll
    for _ in range(10):
        # generate random discrim
        discrim = _raw_discrim()

        # check if anyone is with it
        res = await app.db.fetchval(
            """
            SELECT id
            FROM users
            WHERE username = $1 AND discriminator = $2
            """,
            username,
            discrim,
        )

        # if no user is found with the (username, discrim)
        # pair, then this is unique! return it.
        if res is None:
            return discrim

    return None


async def create_user(username: str, email: str, password: str) -> Tuple[int, str]:
    """Create a single user.

    Generates a distriminator and other information. You can fetch the user
    data back with :meth:`Storage.get_user`.
    """
    new_id = get_snowflake()
    new_discrim = await roll_discrim(username)

    if new_discrim is None:
        raise BadRequest(
            "Unable to register.",
            {"username": "Too many people are with this username."},
        )

    pwd_hash = await hash_data(password)

    try:
        await app.db.execute(
            """
            INSERT INTO users
                (id, email, username, discriminator, password_hash)
            VALUES
                ($1, $2, $3, $4, $5)
            """,
            new_id,
            email,
            username,
            new_discrim,
            pwd_hash,
        )
    except UniqueViolationError:
        raise BadRequest("Email already used.")

    return new_id, pwd_hash


async def _del_from_table(db, table: str, user_id: int):
    """Delete a row from a table."""
    column = {
        "channel_overwrites": "target_user",
        "user_settings": "id",
        "group_dm_members": "member_id",
    }.get(table, "user_id")

    res = await db.execute(
        f"""
    DELETE FROM {table}
    WHERE {column} = $1
    """,
        user_id,
    )

    log.info("Deleting uid {} from {}, res: {!r}", user_id, table, res)


async def delete_user(user_id, *, mass_update: bool = True):
    """Delete a user. Does not disconnect the user."""
    db = app.db

    new_username = f"Deleted User {rand_hex()}"

    # by using a random hex in password_hash
    # we break attempts at using the default '123' password hash
    # to issue valid tokens for deleted users.

    await db.execute(
        """
    UPDATE users
    SET
        username = $1,
        email = NULL,
        mfa_enabled = false,
        verified = false,
        avatar = NULL,
        flags = 0,
        premium_since = NULL,
        phone = '',
        password_hash = $2
    WHERE
        id = $3
    """,
        new_username,
        rand_hex(32),
        user_id,
    )

    # remove the user from various tables
    await _del_from_table(db, "user_settings", user_id)
    await _del_from_table(db, "user_payment_sources", user_id)
    await _del_from_table(db, "user_subscriptions", user_id)
    await _del_from_table(db, "user_payments", user_id)
    await _del_from_table(db, "user_read_state", user_id)
    await _del_from_table(db, "guild_settings", user_id)
    await _del_from_table(db, "guild_settings_channel_overrides", user_id)

    await db.execute(
        """
    DELETE FROM relationships
    WHERE user_id = $1 OR peer_id = $1
    """,
        user_id,
    )

    # DMs are still maintained, but not the state.
    await _del_from_table(db, "dm_channel_state", user_id)

    # NOTE: we don't delete the group dms the user is an owner of...
    # TODO: group dm owner reassign when the owner leaves a gdm
    await _del_from_table(db, "group_dm_members", user_id)

    await _del_from_table(db, "members", user_id)
    await _del_from_table(db, "member_roles", user_id)
    await _del_from_table(db, "channel_overwrites", user_id)

    # after updating the user, we send USER_UPDATE so that all the other
    # clients can refresh their caches on the now-deleted user
    if mass_update:
        await mass_user_update(user_id)


async def user_disconnect(user_id: int):
    """Disconnects the given user's devices."""
    # after removing the user from all tables, we need to force
    # all known user states to reconnect, causing the user to not
    # be online anymore.
    user_states = app.state_manager.user_states(user_id)

    for state in user_states:
        # make it unable to resume
        app.state_manager.remove(state)

        if not state.ws:
            continue

        # force a close, 4000 should make the client reconnect.
        await state.ws.ws.close(4000)

    # force everyone to see the user as offline
    await app.presence.dispatch_pres(user_id, BasePresence(status="offline"))
