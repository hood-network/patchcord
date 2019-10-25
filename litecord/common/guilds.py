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

from quart import current_app as app

from ..snowflake import get_snowflake
from ..permissions import get_role_perms
from ..utils import dict_get, maybe_lazy_guild_dispatch
from ..enums import ChannelType


async def remove_member(guild_id: int, member_id: int):
    """Do common tasks related to deleting a member from the guild,
    such as dispatching GUILD_DELETE and GUILD_MEMBER_REMOVE."""

    await app.db.execute(
        """
        DELETE FROM members
        WHERE guild_id = $1 AND user_id = $2
        """,
        guild_id,
        member_id,
    )

    await app.dispatcher.dispatch_user_guild(
        member_id,
        guild_id,
        "GUILD_DELETE",
        {"guild_id": str(guild_id), "unavailable": False},
    )

    await app.dispatcher.unsub("guild", guild_id, member_id)

    await app.dispatcher.dispatch("lazy_guild", guild_id, "remove_member", member_id)

    await app.dispatcher.dispatch_guild(
        guild_id,
        "GUILD_MEMBER_REMOVE",
        {"guild_id": str(guild_id), "user": await app.storage.get_user(member_id)},
    )


async def remove_member_multi(guild_id: int, members: list):
    """Remove multiple members."""
    for member_id in members:
        await remove_member(guild_id, member_id)


async def create_role(guild_id, name: str, **kwargs):
    """Create a role in a guild."""
    new_role_id = get_snowflake()

    everyone_perms = await get_role_perms(guild_id, guild_id)
    default_perms = dict_get(kwargs, "default_perms", everyone_perms.binary)

    # update all roles so that we have space for pos 1, but without
    # sending GUILD_ROLE_UPDATE for everyone
    await app.db.execute(
        """
    UPDATE roles
    SET
        position = position + 1
    WHERE guild_id = $1
      AND NOT (position = 0)
    """,
        guild_id,
    )

    await app.db.execute(
        """
        INSERT INTO roles (id, guild_id, name, color,
            hoist, position, permissions, managed, mentionable)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        """,
        new_role_id,
        guild_id,
        name,
        dict_get(kwargs, "color", 0),
        dict_get(kwargs, "hoist", False),
        # always set ourselves on position 1
        1,
        int(dict_get(kwargs, "permissions", default_perms)),
        False,
        dict_get(kwargs, "mentionable", False),
    )

    role = await app.storage.get_role(new_role_id, guild_id)

    # we need to update the lazy guild handlers for the newly created group
    await maybe_lazy_guild_dispatch(guild_id, "new_role", role)

    await app.dispatcher.dispatch_guild(
        guild_id, "GUILD_ROLE_CREATE", {"guild_id": str(guild_id), "role": role}
    )

    return role


async def _specific_chan_create(channel_id, ctype, **kwargs):
    if ctype == ChannelType.GUILD_TEXT:
        await app.db.execute(
            """
        INSERT INTO guild_text_channels (id, topic)
        VALUES ($1, $2)
        """,
            channel_id,
            kwargs.get("topic", ""),
        )
    elif ctype == ChannelType.GUILD_VOICE:
        await app.db.execute(
            """
            INSERT INTO guild_voice_channels (id, bitrate, user_limit)
            VALUES ($1, $2, $3)
            """,
            channel_id,
            kwargs.get("bitrate", 64),
            kwargs.get("user_limit", 0),
        )


async def create_guild_channel(
    guild_id: int, channel_id: int, ctype: ChannelType, **kwargs
):
    """Create a channel in a guild."""
    await app.db.execute(
        """
    INSERT INTO channels (id, channel_type)
    VALUES ($1, $2)
    """,
        channel_id,
        ctype.value,
    )

    # calc new pos
    max_pos = await app.db.fetchval(
        """
    SELECT MAX(position)
    FROM guild_channels
    WHERE guild_id = $1
    """,
        guild_id,
    )

    # account for the first channel in a guild too
    max_pos = max_pos or 0

    # all channels go to guild_channels
    await app.db.execute(
        """
    INSERT INTO guild_channels (id, guild_id, name, position)
    VALUES ($1, $2, $3, $4)
    """,
        channel_id,
        guild_id,
        kwargs["name"],
        max_pos + 1,
    )

    # the rest of sql magic is dependant on the channel
    # we're creating (a text or voice or category),
    # so we use this function.
    await _specific_chan_create(channel_id, ctype, **kwargs)


async def delete_guild(guild_id: int):
    """Delete a single guild."""
    await app.db.execute(
        """
    DELETE FROM guilds
    WHERE guilds.id = $1
    """,
        guild_id,
    )

    # Discord's client expects IDs being string
    await app.dispatcher.dispatch(
        "guild",
        guild_id,
        "GUILD_DELETE",
        {
            "guild_id": str(guild_id),
            "id": str(guild_id),
            # 'unavailable': False,
        },
    )

    # remove from the dispatcher so nobody
    # becomes the little memer that tries to fuck up with
    # everybody's gateway
    await app.dispatcher.remove("guild", guild_id)


async def create_guild_settings(guild_id: int, user_id: int):
    """Create guild settings for the user
    joining the guild."""

    # new guild_settings are based off the currently
    # set guild settings (for the guild)
    m_notifs = await app.db.fetchval(
        """
    SELECT default_message_notifications
    FROM guilds
    WHERE id = $1
    """,
        guild_id,
    )

    await app.db.execute(
        """
    INSERT INTO guild_settings
        (user_id, guild_id, message_notifications)
    VALUES
        ($1, $2, $3)
    """,
        user_id,
        guild_id,
        m_notifs,
    )
