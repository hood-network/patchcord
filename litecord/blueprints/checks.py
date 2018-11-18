from quart import current_app as app

from litecord.enums import ChannelType, GUILD_CHANS
from litecord.errors import (
    GuildNotFound, ChannelNotFound, Forbidden, MissingPermissions
)
from litecord.permissions import base_permissions, get_permissions


async def guild_check(user_id: int, guild_id: int):
    """Check if a user is in a guild."""
    joined_at = await app.db.execute("""
    SELECT joined_at
    FROM members
    WHERE user_id = $1 AND guild_id = $2
    """, user_id, guild_id)

    if not joined_at:
        raise GuildNotFound('guild not found')


async def guild_owner_check(user_id: int, guild_id: int):
    """Check if a user is the owner of the guild."""
    owner_id = await app.db.fetchval("""
    SELECT owner_id
    FROM guilds
    WHERE guilds.id = $1
    """, guild_id)

    if not owner_id:
        raise GuildNotFound()

    if user_id != owner_id:
        raise Forbidden('You are not the owner of the guild')


async def channel_check(user_id, channel_id):
    """Check if the current user is authorized
    to read the channel's information."""
    chan_type = await app.storage.get_chan_type(channel_id)

    if chan_type is None:
        raise ChannelNotFound(f'channel type not found')

    ctype = ChannelType(chan_type)

    if ctype in GUILD_CHANS:
        guild_id = await app.db.fetchval("""
        SELECT guild_id
        FROM guild_channels
        WHERE guild_channels.id = $1
        """, channel_id)

        await guild_check(user_id, guild_id)
        return ctype, guild_id

    if ctype == ChannelType.DM:
        peer_id = await app.storage.get_dm_peer(channel_id, user_id)
        return ctype, peer_id


async def guild_perm_check(user_id, guild_id, permission: str):
    """Check guild permissions for a user."""
    base_perms = await base_permissions(user_id, guild_id)
    hasperm = getattr(base_perms.bits, permission)

    if not hasperm:
        raise MissingPermissions('Missing permissions.')

    return bool(hasperm)


async def channel_perm_check(user_id, channel_id,
                             permission: str, raise_err=True):
    """Check channel permissions for a user."""
    base_perms = await get_permissions(user_id, channel_id)
    hasperm = getattr(base_perms.bits, permission)

    if not hasperm and raise_err:
        raise MissingPermissions('Missing permissions.')

    return bool(hasperm)
