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

from typing import Union, List, Optional

from quart import current_app as app

from litecord.enums import ChannelType, GUILD_CHANS
from litecord.errors import (
    GuildNotFound,
    ChannelNotFound,
    Forbidden,
    MissingPermissions,
)
from litecord.permissions import base_permissions, get_permissions


async def guild_check(user_id: int, guild_id: int):
    """Check if a user is in a guild."""
    joined_at = await app.db.fetchval(
        """
    SELECT joined_at
    FROM members
    WHERE user_id = $1 AND guild_id = $2
    """,
        user_id,
        guild_id,
    )

    if not joined_at:
        raise GuildNotFound("guild not found")


async def guild_owner_check(user_id: int, guild_id: int):
    """Check if a user is the owner of the guild."""
    owner_id = await app.db.fetchval(
        """
    SELECT owner_id
    FROM guilds
    WHERE guilds.id = $1
    """,
        guild_id,
    )

    if not owner_id:
        raise GuildNotFound()

    if user_id != owner_id:
        raise Forbidden("You are not the owner of the guild")


async def channel_check(
    user_id, channel_id, *, only: Optional[Union[ChannelType, List[ChannelType]]] = None
):
    """Check if the current user is authorized
    to read the channel's information."""
    chan_type = await app.storage.get_chan_type(channel_id)

    if chan_type is None:
        raise ChannelNotFound("channel type not found")

    ctype = ChannelType(chan_type)

    if (only is not None) and not isinstance(only, list):
        only = [only]

    if (only is not None) and ctype not in only:
        raise ChannelNotFound("invalid channel type")

    if ctype in GUILD_CHANS:
        guild_id = await app.db.fetchval(
            """
        SELECT guild_id
        FROM guild_channels
        WHERE guild_channels.id = $1
        """,
            channel_id,
        )
        assert guild_id is not None
        await guild_check(user_id, guild_id)
        return ctype, guild_id

    if ctype == ChannelType.DM:
        peer_id = await app.storage.get_dm_peer(channel_id, user_id)
        return ctype, peer_id

    if ctype == ChannelType.GROUP_DM:
        owner_id = await app.db.fetchval(
            """
        SELECT owner_id
        FROM group_dm_channels
        WHERE id = $1
        """,
            channel_id,
        )

        return ctype, owner_id


async def _max_role_position(guild_id, member_id) -> Optional[int]:
    return await app.db.fetchval(
        """
        SELECT MAX(roles.position)
        FROM member_roles
        JOIN roles ON roles.id = member_roles.role_id
        WHERE member_roles.guild_id = $1 AND
            member_roles.user_id = $2
        """,
        guild_id,
        member_id,
    )


async def _validate_target_member(
    guild_id: int, user_id: int, target_member_id: int
) -> bool:
    owner_id = await app.storage.db.fetchval(
        """
        SELECT owner_id
        FROM guilds
        WHERE id = $1
        """,
        guild_id,
    )
    assert owner_id is not None

    # owners have all permissions
    # if doing an action as an owner, it always works
    # if doing an action TO an owner, it always fails
    if user_id == owner_id:
        return True

    if target_member_id == owner_id:
        return False

    # there is no internal function to fetch full role objects
    # (likely because it would be too expensive to do it here),
    # so instead do a raw sql query.

    target_max_position = await _max_role_position(guild_id, target_member_id)
    user_max_position = await _max_role_position(guild_id, user_id)

    assert target_max_position is not None
    assert user_max_position is not None

    return user_max_position > target_max_position


async def guild_perm_check(
    user_id,
    guild_id,
    permission: str,
    target_member_id: Optional[int] = None,
    raise_err: bool = True,
) -> bool:
    """Check guild permissions for a user.

    Accepts optional target argument for actions that are done TO another member
    in the guild."""
    base_perms = await base_permissions(user_id, guild_id)
    hasperm = getattr(base_perms.bits, permission)

    # if we have the PERM and there's a target member involved,
    # check on the target's max(role.position), if its equal or greater,
    # raise MissingPermissions
    if hasperm and target_member_id:
        hasperm = await _validate_target_member(guild_id, user_id, target_member_id)

    if not hasperm and raise_err:
        raise MissingPermissions("Missing permissions.")

    return bool(hasperm)


# TODO add target semantics
async def channel_perm_check(
    user_id,
    channel_id,
    permission: str,
    raise_err=True,
):
    """Check channel permissions for a user."""
    base_perms = await get_permissions(user_id, channel_id)
    hasperm = getattr(base_perms.bits, permission)

    if not hasperm and raise_err:
        raise MissingPermissions("Missing permissions.")

    return bool(hasperm)
