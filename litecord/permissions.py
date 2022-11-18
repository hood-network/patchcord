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

import ctypes
from dataclasses import dataclass
from typing import Optional, Union, TYPE_CHECKING

if TYPE_CHECKING:
    from litecord.typing_hax import app
else:
    from quart import current_app as app

# so we don't keep repeating the same
# type for all the fields
_i = ctypes.c_uint8


class _RawPermsBits(ctypes.LittleEndianStructure):
    """raw bitfield for discord's permission number."""

    _fields_ = [
        ("create_invites", _i, 1),
        ("kick_members", _i, 1),
        ("ban_members", _i, 1),
        ("administrator", _i, 1),
        ("manage_channels", _i, 1),
        ("manage_guild", _i, 1),
        ("add_reactions", _i, 1),
        ("view_audit_log", _i, 1),
        ("priority_speaker", _i, 1),
        ("stream", _i, 1),
        ("read_messages", _i, 1),
        ("send_messages", _i, 1),
        ("send_tts", _i, 1),
        ("manage_messages", _i, 1),
        ("embed_links", _i, 1),
        ("attach_files", _i, 1),
        ("read_history", _i, 1),
        ("mention_everyone", _i, 1),
        ("external_emojis", _i, 1),
        ("view_guild_insights", _i, 1),
        ("connect", _i, 1),
        ("speak", _i, 1),
        ("mute_members", _i, 1),
        ("deafen_members", _i, 1),
        ("move_members", _i, 1),
        ("use_voice_activation", _i, 1),
        ("change_nickname", _i, 1),
        ("manage_nicknames", _i, 1),
        ("manage_roles", _i, 1),
        ("manage_webhooks", _i, 1),
        ("manage_emojis", _i, 1),
    ]


class Permissions(ctypes.Union):
    """Main permissions class. Holds helper functions to convert between
    the bitfield and an integer, etc.

    Parameters
    ----------
    val
        The permissions value as an integer.
    """

    _fields_ = [("bits", _RawPermsBits), ("binary", ctypes.c_uint64)]

    def __init__(self, val: Union[str, int]):
        # always coerce to int, even when the user gives us a str, because
        # python ints are infinity-sized (yes, yes, the memory concerns, yes)
        self.binary = int(val)

    def __repr__(self):
        return f"<Permissions binary={self.binary}>"

    def __int__(self):
        return self.binary


ALL_PERMISSIONS = Permissions(0b01111111111111111111111111111111)
EMPTY_PERMISSIONS = Permissions(0)


@dataclass
class Target:
    type: int
    user_id: Optional[int]
    role_id: Optional[int]

    @property
    def is_user(self):
        return self.type == 1

    @property
    def is_role(self):
        return self.type == 0


async def get_role_perms(guild_id, role_id, storage=None) -> Permissions:
    """Get the raw :class:`Permissions` object for a role."""
    if not storage:
        storage = app.storage

    perms = await storage.db.fetchval(
        """
    SELECT permissions
    FROM roles
    WHERE guild_id = $1 AND id = $2
    """,
        guild_id,
        role_id,
    )

    assert perms is not None

    return Permissions(perms)


async def base_permissions(member_id, guild_id, storage=None) -> Permissions:
    """Compute the base permissions for a given user.

    Base permissions are
        (permissions from @everyone role) +
        (permissions from any other role the member has)

    This will give ALL_PERMISSIONS if base permissions
    has the Administrator bit set.
    """

    if not storage:
        storage = app.storage

    owner_id = await storage.db.fetchval(
        """
    SELECT owner_id
    FROM guilds
    WHERE id = $1
    """,
        guild_id,
    )

    if owner_id == member_id:
        return ALL_PERMISSIONS

    # get permissions for @everyone
    permissions = await get_role_perms(guild_id, guild_id, storage)

    role_ids = await storage.db.fetch(
        """
    SELECT role_id
    FROM member_roles
    WHERE guild_id = $1 AND user_id = $2
    """,
        guild_id,
        member_id,
    )

    role_perms = []

    for row in role_ids:
        rperm = await storage.db.fetchval(
            """
        SELECT permissions
        FROM roles
        WHERE id = $1
        """,
            row["role_id"],
        )

        role_perms.append(rperm)

    for perm_num in role_perms:
        permissions.binary |= perm_num

    if permissions.bits.administrator:
        return ALL_PERMISSIONS

    return permissions


def overwrite_mix(perms: Permissions, overwrite: dict) -> Permissions:
    """Mix a single permission with a single overwrite."""
    # we make a copy of the binary representation
    # so we don't modify the old perms in-place
    # which could be an unwanted side-effect
    result = perms.binary

    # negate the permissions that are denied
    result &= ~overwrite["deny"]

    # combine the permissions that are allowed
    result |= overwrite["allow"]

    return Permissions(result)


def overwrite_find_mix(
    perms: Permissions, overwrites: dict, target_id: int
) -> Permissions:
    """Mix a given permission with a given overwrite.

    Returns the given permission if an overwrite is not found.

    Parameters
    ----------
    perms
        The permissions for the given target.
    overwrites
        The overwrites for the given actor (mostly channel).
    target_id
        The target's ID in the overwrites dict.

    Returns
    -------
    Permissions
        The mixed permissions object.
    """
    overwrite = overwrites.get(target_id)

    if overwrite:
        # only mix if overwrite found
        return overwrite_mix(perms, overwrite)

    return perms


async def role_permissions(
    guild_id: int, role_id: int, channel_id: int, storage=None
) -> Permissions:
    """Get the permissions for a role, in relation to a channel"""
    if not storage:
        storage = app.storage

    perms = await get_role_perms(guild_id, role_id, storage)

    overwrite = await storage.db.fetchrow(
        """
    SELECT allow, deny
    FROM channel_overwrites
    WHERE channel_id = $1 AND target_type = $2 AND target_role = $3
    """,
        channel_id,
        1,
        role_id,
    )

    if overwrite:
        perms = overwrite_mix(perms, overwrite)

    return perms


async def compute_overwrites(
    base_perms: Permissions,
    user_id,
    channel_id: int,
    guild_id: Optional[int] = None,
    storage=None,
):
    """Compute the permissions in the context of a channel."""
    if not storage:
        storage = app.storage

    if base_perms.bits.administrator:
        return ALL_PERMISSIONS

    perms = base_perms

    # list of overwrites
    overwrites = await storage.chan_overwrites(channel_id, safe=False)

    # if the channel isn't a guild, we should just return
    # ALL_PERMISSIONS. the old approach was calling guild_from_channel
    # again, but it is already passed by get_permissions(), so its
    # redundant.
    if not guild_id:
        return ALL_PERMISSIONS

    # make it a map for better usage
    overwrites = {o["id"]: o for o in overwrites}

    perms = overwrite_find_mix(perms, overwrites, guild_id)

    # apply role specific overwrites
    allow, deny = 0, 0

    # fetch roles from user and convert to int
    role_ids = await storage.get_member_role_ids(guild_id, user_id)

    # make the allow and deny binaries
    for role_id in role_ids:
        overwrite = overwrites.get(role_id)
        if overwrite:
            allow |= overwrite["allow"]
            deny |= overwrite["deny"]

    # final step for roles: mix
    perms = overwrite_mix(perms, {"allow": allow, "deny": deny})

    # apply member specific overwrites
    perms = overwrite_find_mix(perms, overwrites, user_id)

    return perms


async def get_permissions(member_id: int, channel_id, *, storage=None) -> Permissions:
    """Get the permissions for a user in a channel."""
    if not storage:
        storage = app.storage

    guild_id = await storage.guild_from_channel(channel_id)

    # for non guild channels
    if not guild_id:
        return ALL_PERMISSIONS

    base_perms = await base_permissions(member_id, guild_id, storage)

    return await compute_overwrites(
        base_perms, member_id, channel_id, guild_id, storage
    )
